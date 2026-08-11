from agentready.report_components import (
    render_category_card,
    render_disclosure,
    render_progress_bar,
    render_remediation_block,
    render_recommendation_list,
    render_report_navigation,
    render_report_toolbar,
    render_report_table,
    render_score_meter,
    render_section,
    render_status_badge,
)


def test_status_badge_escapes_label_and_keeps_textual_semantics():
    output = render_status_badge("warn", "<Review>")

    assert "status-warn" in output
    assert "aria-hidden='true'>!</span>" in output
    assert "&lt;Review&gt;" in output


def test_score_and_progress_components_bound_values_and_escape_labels():
    score = render_score_meter(140, "<Score>")
    progress = render_progress_bar(-5, "<Category>")

    assert "value='100'" in score
    assert ">100/100</meter>" in score
    assert ">100/100</strong>" in score
    assert "&lt;Score&gt;" in score
    assert "aria-valuenow='0'" in progress
    assert "&lt;Category&gt;" in progress


def test_section_and_disclosure_components_expose_explicit_relationships():
    section = render_section("summary", "Summary", "<p>facts</p>")
    disclosure = render_disclosure("recommendations", "Recommendations", "<ol></ol>")

    assert "aria-labelledby='summary-title'" in section
    assert "<h2 id='summary-title'>Summary</h2>" in section
    assert "<summary id='recommendations'><h3>Recommendations</h3></summary>" in disclosure


def test_category_card_reuses_progress_semantics_and_escapes_labels():
    output = render_category_card("<Category>", "Review <details>", "80%", 80)

    assert "role='progressbar'" in output
    assert "aria-valuenow='80'" in output
    assert "&lt;Category&gt;" in output
    assert "Review &lt;details&gt;" in output


def test_report_table_component_escapes_headers_and_preserves_row_semantics():
    output = render_report_table("checks", "<Checks>", ("<Status>", "Result"), "<tr><td>pass</td></tr>")

    assert "id='checks'" in output
    assert "<caption>&lt;Checks&gt;</caption>" in output
    assert "<th scope='col'>&lt;Status&gt;</th>" in output
    assert "<tr><td>pass</td></tr>" in output


def test_recommendation_list_component_preserves_order_and_escapes_empty_state():
    output = render_recommendation_list("<li>First</li><li>Second</li>", "<No recommendations>")
    empty = render_recommendation_list("", "<No recommendations>")

    assert output == "<ol class='recommendation-list'><li>First</li><li>Second</li></ol>"
    assert "&lt;No recommendations&gt;" in empty


def test_remediation_block_preserves_rendered_sections_and_escapes_empty_state():
    output = render_remediation_block("<section>Fix</section>", "<No remediation>")
    empty = render_remediation_block("", "<No remediation>")

    assert output == "<section>Fix</section>"
    assert empty == "<p>&lt;No remediation&gt;</p>"


def test_report_navigation_component_escapes_targets_and_labels():
    output = render_report_navigation((("summary", "<Summary>"),), "<Report navigation>")

    assert output == "<nav class='report-nav' aria-label='&lt;Report navigation&gt;'><a href='#summary'>&lt;Summary&gt;</a></nav>"


def test_report_toolbar_component_preserves_language_control_and_escapes_label():
    output = render_report_toolbar("<Language>", "<option value='en'>English</option>")

    assert output == "<div class='toolbar'><label for='lang'>&lt;Language&gt;:</label><select id='lang'><option value='en'>English</option></select></div>"
