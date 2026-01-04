"""
Tasks page - Task management interface
"""

import streamlit as st
from datetime import datetime, timedelta

def render_tasks_page():
    """Render the tasks page"""
    st.markdown("## ✅ Tasks")
    
    # Task filters and controls
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        task_filter = st.selectbox(
            "Filter by Status",
            ["All", "Pending", "In Progress", "Completed"],
            key="task_filter"
        )
    
    with col2:
        priority_filter = st.selectbox(
            "Filter by Priority",
            ["All", "High", "Medium", "Low"],
            key="priority_filter"
        )
    
    with col3:
        if st.button("➕ Add Task", key="add_task_btn"):
            st.session_state.show_add_task = True
    
    st.divider()
    
    # Add task form
    if st.session_state.get("show_add_task", False):
        with st.form("add_task_form"):
            title = st.text_input("Task Title", key="task_title")
            description = st.text_area("Description", key="task_desc")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                priority = st.selectbox("Priority", ["Low", "Medium", "High"], key="task_priority")
            with col2:
                due_date = st.date_input("Due Date", value=datetime.now() + timedelta(days=1), key="task_due")
            with col3:
                status = st.selectbox("Status", ["Pending", "In Progress", "Completed"], key="task_status")
            
            if st.form_submit_button("Create Task"):
                new_task = {
                    "id": len(st.session_state.tasks),
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "due_date": str(due_date),
                    "status": status
                }
                st.session_state.tasks.append(new_task)
                st.session_state.show_add_task = False
                st.success("Task created successfully!")
                st.rerun()
    
    st.divider()
    
    # Task list
    if st.session_state.tasks:
        for idx, task in enumerate(st.session_state.tasks):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.markdown(f"### {task['title']}")
                st.markdown(f"**Status:** {task['status']} | **Priority:** {task['priority']} | **Due:** {task['due_date']}")
                if task['description']:
                    st.write(task['description'])
            
            with col2:
                if st.button("✏️ Edit", key=f"edit_task_{idx}"):
                    st.session_state.editing_task = idx
                if st.button("🗑️ Delete", key=f"delete_task_{idx}"):
                    st.session_state.tasks.pop(idx)
                    st.rerun()
            
            st.divider()
    else:
        st.info("No tasks yet. Create one to get started!")
