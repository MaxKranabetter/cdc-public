import streamlit as st

def interactive_dropdown(label, items, unique_key="dropdown"):
    focus_key = f"{unique_key}_focused"
    toggle_key = f"{unique_key}_toggled_off"

    if focus_key not in st.session_state:
        st.session_state[focus_key] = None
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = set() # Set for efficient lookups

    # 2. Define Callbacks to handle logic before the UI renders
    def toggle_focus(item):
        # If already focused, unfocus it. Otherwise, set it as focused.
        if st.session_state[focus_key] == item:
            st.session_state[focus_key] = None
        else:
            st.session_state[focus_key] = item

    def toggle_consideration(item):
        if item in st.session_state[toggle_key]:
            # Restore it
            st.session_state[toggle_key].remove(item)
        else:
            # Remove it from consideration
            st.session_state[toggle_key].add(item)
            # If we disable an item, ensure it also loses focus
            if st.session_state[focus_key] == item:
                st.session_state[focus_key] = None

    # 3. Render the UI
    with st.popover(label, use_container_width=True):
        if not items:
            st.write("No items available.")
            return None, set()
            
        for item in items:
            # Determine current state for this item
            is_focused = (st.session_state[focus_key] == item)
            is_disabled = (item in st.session_state[toggle_key])

            col_text, col_btn1, col_btn2 = st.columns([0.5, 0.25, 0.25], vertical_alignment="center")
            
            with col_text:
                # UI Representation of State
                display_text = item
                if is_focused:
                    display_text = f"**🎯 {item}**" # Highlight focused item
                
                if is_disabled:
                    # Grey out and strike through if removed from consideration
                    st.markdown(f":gray[~{display_text}~]") 
                else:
                    st.markdown(display_text)
                    
            with col_btn1:
                # Focus Button
                btn_label = "Unfocus" if is_focused else "Focus"
                st.button(
                    btn_label, 
                    key=f"{unique_key}_focus_{item}", 
                    disabled=is_disabled, # Cannot focus a disabled item
                    on_click=toggle_focus,
                    args=(item,)
                )
                    
            with col_btn2:
                # Toggle/Remove Button
                btn_label = "Restore" if is_disabled else "Remove"
                st.button(
                    btn_label, 
                    key=f"{unique_key}_toggle_{item}", 
                    type="secondary" if is_disabled else "primary",
                    on_click=toggle_consideration,
                    args=(item,)
                )
                
    # Return the current state to the main app so it can react to changes
    return st.session_state[focus_key], st.session_state[toggle_key]