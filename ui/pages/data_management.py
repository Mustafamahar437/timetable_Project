"""
ui/pages/data_management.py
===========================
University Data Management page for viewing and modifying faculty, courses, rooms, and groups.
"""

from __future__ import annotations
import streamlit as st
from ui import theme
import pandas as pd


def render(db_manager, session_state):
    theme.page_header("📊 University Data Management", "Manage faculty, courses, classrooms/laboratories, and student groups stored in the university database.")

    tab_teachers, tab_courses, tab_rooms, tab_groups = st.tabs([
        "👨‍🏫 Faculty (Teachers)", 
        "📚 Courses", 
        "🏛️ Rooms & Labs", 
        "👥 Student Groups"
    ])

    # 1. Teachers Tab
    with tab_teachers:
        st.subheader("Faculty Registry")
        teachers = db_manager.get_teachers()
        if teachers:
            df_t = pd.DataFrame(teachers)
            st.dataframe(df_t, width="stretch")
        else:
            st.info("No faculty registered yet.")

        with st.expander("➕ Register New Faculty Member"):
            with st.form("add_teacher_form"):
                t_name = st.text_input("Short Name / Identifier (e.g., Ahmed, Sara, Bilal)")
                t_email = st.text_input("Email Address")
                t_dept = st.selectbox("Department", ["Computer Science", "Mathematics", "Management", "Social Sciences", "Natural Sciences"])
                if st.form_submit_button("Add Teacher"):
                    if t_name.strip():
                        db_manager.add_teacher(t_name.strip(), t_email.strip(), t_dept)
                        st.success(f"Teacher '{t_name}' registered successfully.")
                        st.rerun()
                    else:
                        st.error("Teacher name cannot be empty.")

    # 2. Courses Tab
    with tab_courses:
        st.subheader("Course Catalog")
        courses = db_manager.get_courses()
        if courses:
            df_c = pd.DataFrame(courses)
            st.dataframe(df_c, width="stretch")
        else:
            st.info("No courses registered yet.")

        with st.expander("➕ Add New Course"):
            with st.form("add_course_form"):
                c_id = st.text_input("Course ID (e.g., CS101, CS201)")
                c_name = st.text_input("Course Title (e.g., Data Structures)")
                c_dept = st.selectbox("Department", ["Computer Science", "Mathematics", "Management", "Social Sciences", "Natural Sciences"], key="c_dept")
                c_cr = st.number_input("Credit Hours", min_value=1, max_value=6, value=3)
                c_stu = st.number_input("Enrolled Students", min_value=5, max_value=200, value=40)
                c_dpw = st.number_input("Sessions Per Week", min_value=1, max_value=5, value=2)
                c_dur = st.number_input("Session Duration (Hours)", min_value=1, max_value=3, value=1)
                teacher_options = [t["teacher_id"] for t in db_manager.get_teachers()]
                room_options = [r["room_id"] for r in db_manager.get_rooms()]
                c_tid = st.selectbox("Teacher ID (existing faculty)", teacher_options)
                c_rid = st.selectbox("Room ID (existing room)", room_options)
                if st.form_submit_button("Add Course"):
                    if c_id.strip() and c_name.strip():
                        db_manager.add_course(c_id.strip(), c_name.strip(), c_dept, int(c_cr), int(c_stu), int(c_dpw), int(c_dur), c_tid or "", c_rid or "")
                        st.success(f"Course '{c_id}' added successfully.")
                        st.rerun()
                    else:
                        st.error("Course ID and title are required.")

    # 3. Rooms Tab
    with tab_rooms:
        st.subheader("Rooms & Facilities")
        rooms = db_manager.get_rooms()
        if rooms:
            df_r = pd.DataFrame(rooms)
            st.dataframe(df_r, width="stretch")
        else:
            st.info("No rooms registered yet.")

        with st.expander("➕ Add Classroom or Laboratory"):
            with st.form("add_room_form"):
                r_id = st.text_input("Room ID (e.g., CR1, Lab1, LH1)")
                r_name = st.text_input("Full Room Description")
                r_cap = st.number_input("Seating Capacity", min_value=10, max_value=500, value=50)
                r_type = st.selectbox("Facility Type", ["LECTURE", "LAB", "AUDITORIUM", "SEMINAR"])
                if st.form_submit_button("Add Room"):
                    if r_id.strip():
                        db_manager.add_room(r_id.strip(), r_name.strip(), int(r_cap), r_type)
                        st.success(f"Room '{r_id}' added successfully.")
                        st.rerun()
                    else:
                        st.error("Room ID cannot be empty.")

    # 4. Student Groups Tab
    with tab_groups:
        st.subheader("Student Batches & Groups")
        groups = db_manager.get_student_groups()
        if groups:
            df_g = pd.DataFrame(groups)
            st.dataframe(df_g, width="stretch")
        else:
            st.info("No student groups registered yet.")

        with st.expander("➕ Register Student Group"):
            with st.form("add_group_form"):
                g_id = st.text_input("Group ID (e.g., CS-1A, CS-2A)")
                g_name = st.text_input("Group Batch Name")
                g_size = st.number_input("Number of Students", min_value=10, max_value=150, value=40)
                g_dept = st.selectbox("Department", ["Computer Science", "Mathematics", "Management"], key="g_dept")
                if st.form_submit_button("Add Group"):
                    if g_id.strip():
                        db_manager.add_student_group(g_id.strip(), g_name.strip(), int(g_size), g_dept)
                        st.success(f"Group '{g_id}' registered successfully.")
                        st.rerun()
                    else:
                        st.error("Group ID cannot be empty.")
