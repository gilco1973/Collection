from kb_librarian.catalog.frontmatter import parse_frontmatter, render_frontmatter


def test_parse_frontmatter_splits_meta_and_body():
    text = "---\ntitle: T\ntags: [a, b]\n---\n# Body\n"
    meta, body = parse_frontmatter(text)
    assert meta == {"title": "T", "tags": ["a", "b"]}
    assert body == "# Body\n"


def test_parse_frontmatter_without_block_returns_empty_meta():
    meta, body = parse_frontmatter("# Just body\n")
    assert meta == {}
    assert body == "# Just body\n"


def test_parse_frontmatter_rejects_non_mapping():
    meta, body = parse_frontmatter("---\n- a\n- b\n---\nbody")
    assert meta == {"_parse_error": "frontmatter is not a mapping"}
    assert body == "body"


def test_parse_frontmatter_reports_yaml_error():
    meta, _ = parse_frontmatter("---\ntitle: a: b\n---\nbody")
    assert "_parse_error" in meta


def test_render_round_trips():
    meta = {"title": "T", "reviewed": "2026-01-01", "tags": ["x"]}
    text = render_frontmatter(meta, "# Body\n")
    parsed, body = parse_frontmatter(text)
    assert parsed["title"] == "T"
    assert str(parsed["reviewed"]) == "2026-01-01"
    assert body == "# Body\n"
