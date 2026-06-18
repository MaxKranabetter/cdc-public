from .intake_wizard import render_intake_wizard

def location_input_form(coverage_floodmap_path: str) -> None:
    render_intake_wizard(coverage_floodmap_path)