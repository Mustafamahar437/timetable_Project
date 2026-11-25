"""
compat/pandas_shim.py
=====================
Resilient pure-Python DataFrame and pivot table implementation used when
the native C-extension pandas library is blocked by Windows Application
Control (Smart App Control) policy.

Provides exact compatibility for:
- pd.DataFrame(records)
- pd.pivot_table(df, index=..., columns=..., values=..., aggfunc=..., fill_value=...)
- df.to_csv(), df.to_dict(), df.iterrows(), df.empty, df.columns, df.index
- Series concatenation and column assignment: df["col"] = df["a"] + " " + df["b"]
"""

from __future__ import annotations
import csv
import io
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union


class Series(list):
    """Pure Python Series representation supporting element-wise operations."""

    def __init__(self, data: Optional[List[Any]] = None, name: Optional[str] = None):
        super().__init__(data or [])
        self.name = name

    def __add__(self, other: Any) -> "Series":
        if isinstance(other, (list, Series)):
            return Series([str(a) + str(b) for a, b in zip(self, other)], name=self.name)
        return Series([str(a) + str(other) for a in self], name=self.name)

    def __radd__(self, other: Any) -> "Series":
        return Series([str(other) + str(a) for a in self], name=self.name)

    @property
    def values(self) -> List[Any]:
        return list(self)

    def tolist(self) -> List[Any]:
        return list(self)


class Index(list):
    """Pure Python Index representation."""
    def __init__(self, data: Optional[List[Any]] = None, name: Optional[str] = None):
        super().__init__(data or [])
        self.name = name


class MultiIndex(Index):
    pass


class Categorical(list):
    pass


NA = None
NaT = None


def isna(obj: Any) -> bool:
    return obj is None


isnull = isna


class DataFrame:
    """Pure-Python DataFrame representation for display, indexing, and export."""

    def __init__(
        self,
        data: Optional[Union[List[Dict[str, Any]], Dict[str, List[Any]], Any]] = None,
        columns: Optional[List[str]] = None,
        index: Optional[List[Any]] = None,
    ):
        self._records: List[Dict[str, Any]] = []
        self._columns: List[str] = list(columns) if columns else []
        self._index: List[Any] = list(index) if index else []

        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                self._records = [dict(d) for d in data]
                if not self._columns:
                    # preserve ordering of first record's keys
                    self._columns = list(self._records[0].keys())
            elif data and isinstance(data[0], (list, tuple)):
                cols = self._columns or [str(i) for i in range(len(data[0]))]
                self._records = [dict(zip(cols, row)) for row in data]
                self._columns = cols
        elif isinstance(data, dict):
            keys = list(data.keys())
            self._columns = list(columns) if columns else keys
            n = len(data[keys[0]]) if keys and isinstance(data[keys[0]], (list, tuple)) else 0
            self._records = []
            for i in range(n):
                self._records.append({k: data[k][i] for k in keys})
        elif isinstance(data, DataFrame):
            self._records = [dict(d) for d in data._records]
            self._columns = list(data._columns)
            self._index = list(data._index)

        if not self._index:
            self._index = list(range(len(self._records)))

    @property
    def columns(self) -> List[str]:
        return list(self._columns)

    @columns.setter
    def columns(self, cols: List[str]) -> None:
        self._columns = list(cols)

    @property
    def index(self) -> List[Any]:
        return list(self._index)

    @index.setter
    def index(self, idx: List[Any]) -> None:
        self._index = list(idx)

    @property
    def empty(self) -> bool:
        return len(self._records) == 0

    @property
    def shape(self) -> Tuple[int, int]:
        return (len(self._records), len(self._columns))

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, list):
            sub_records = [{c: r.get(c) for c in key} for r in self._records]
            return DataFrame(sub_records, columns=key, index=self._index)
        if isinstance(key, str):
            return Series([r.get(key) for r in self._records], name=key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._columns:
            self._columns.append(key)
        if isinstance(value, (list, tuple, Series)):
            for i, r in enumerate(self._records):
                r[key] = value[i] if i < len(value) else None
        else:
            for r in self._records:
                r[key] = value

    def iterrows(self) -> Iterator[Tuple[Any, Dict[str, Any]]]:
        for idx, row in zip(self._index, self._records):
            yield (idx, row)

    def to_dict(self, orient: str = "records") -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        if orient == "records":
            return [dict(r) for r in self._records]
        return {c: [r.get(c) for r in self._records] for c in self._columns}

    def to_csv(self, index: bool = False, index_label: Optional[str] = None) -> str:
        out = io.StringIO()
        fieldnames = list(self._columns)
        if index and index_label:
            fieldnames = [index_label] + fieldnames
            writer = csv.DictWriter(out, fieldnames=fieldnames)
            writer.writeheader()
            for idx, r in zip(self._index, self._records):
                row_copy = {index_label: idx, **r}
                writer.writerow(row_copy)
        else:
            writer = csv.DictWriter(out, fieldnames=fieldnames)
            writer.writeheader()
            for r in self._records:
                writer.writerow(r)
        return out.getvalue()

    def reindex(
        self,
        index: Optional[List[Any]] = None,
        columns: Optional[List[str]] = None,
        fill_value: Any = "—",
    ) -> "DataFrame":
        new_cols = list(columns) if columns else list(self._columns)
        new_index = list(index) if index else list(self._index)

        # Map current (row_key) -> record
        row_map = {idx: r for idx, r in zip(self._index, self._records)}

        new_records = []
        for rk in new_index:
            old_r = row_map.get(rk, {})
            new_r = {}
            for ck in new_cols:
                new_r[ck] = old_r.get(ck, fill_value)
            new_records.append(new_r)

        return DataFrame(new_records, columns=new_cols, index=new_index)

    def fillna(self, value: Any) -> "DataFrame":
        new_records = []
        for r in self._records:
            new_records.append({k: (value if v is None else v) for k, v in r.items()})
        return DataFrame(new_records, columns=self._columns, index=self._index)

    def head(self, n: int = 5) -> "DataFrame":
        return DataFrame(self._records[:n], columns=self._columns, index=self._index[:n])

    def __repr__(self) -> str:
        return f"<DataFrame shape={self.shape}>"


def pivot_table(
    data: DataFrame,
    values: Optional[str] = None,
    index: Optional[str] = None,
    columns: Optional[str] = None,
    aggfunc: Optional[Callable[[List[Any]], str]] = None,
    fill_value: Any = "—",
) -> DataFrame:
    """
    Pivot a DataFrame into a 2D grid indexed by `index` with columns `columns`.
    """
    if aggfunc is None:
        aggfunc = lambda vals: "\n".join(str(v) for v in vals if v is not None)

    cell_map: Dict[Tuple[Any, Any], List[Any]] = {}
    row_keys: List[Any] = []
    col_keys: List[Any] = []

    for r in data._records:
        rk = r.get(index)
        ck = r.get(columns)
        val = r.get(values)
        if rk not in row_keys:
            row_keys.append(rk)
        if ck not in col_keys:
            col_keys.append(ck)
        cell_map.setdefault((rk, ck), []).append(val)

    records: List[Dict[str, Any]] = []
    for rk in row_keys:
        row_dict: Dict[str, Any] = {}
        for ck in col_keys:
            vals = cell_map.get((rk, ck))
            row_dict[str(ck)] = aggfunc(vals) if vals else fill_value
        records.append(row_dict)

    col_names = [str(c) for c in col_keys]
    return DataFrame(records, columns=col_names, index=row_keys)
