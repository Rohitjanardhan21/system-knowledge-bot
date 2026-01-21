def render_stack_text(stack):
    lines = []
    lines.append("Reasoning Trace:\n")

    for item in stack:
        lines.append(f"[{item['layer']}]")
        for line in item["content"]:
            lines.append(f"  - {line}")
        lines.append("")

def render_stack_html(stack):
    html = "<div class='stack'>"

    for item in stack:
        html += f"<div class='layer'><h3>{item['layer']}</h3><ul>"
        for line in item["content"]:
            html += f"<li>{line}</li>"
        html += "</ul></div>"

    html += "</div>"
    return html
      

    return "\n".join(lines)
