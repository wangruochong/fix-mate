from fix_mate.engine.diffs import parse_diff

MODIFIED = """diff --git a/a.txt b/a.txt
index 1111111..2222222 100644
--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,3 @@
 line1
-line2
+CHANGED
 line3
"""


def test_modified_file():
    [f] = parse_diff(MODIFIED)
    assert (f.name, f.additions, f.deletions) == ("a.txt", 1, 1)
    assert [x.kind for x in f.lines] == ["hunk", "ctx", "del", "add", "ctx"]
    assert f.lines[2].text == "-line2"  # 保留 +/-/空格前缀


def test_new_file_and_several_files():
    text = (
        MODIFIED
        + "diff --git a/dir/new.ts b/dir/new.ts\nnew file mode 100644\n--- /dev/null\n+++ b/dir/new.ts\n@@ -0,0 +1 @@\n+hi\n"
    )
    files = parse_diff(text)
    assert [f.name for f in files] == ["a.txt", "dir/new.ts"]
    assert (files[1].additions, files[1].deletions) == (1, 0)


def test_removed_sql_comment_is_a_code_line_not_a_file_header():
    text = "diff --git a/q.sql b/q.sql\n--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,2 @@\n--- old comment\n+++ new comment\n select 1;\n"
    [f] = parse_diff(text)
    assert (f.additions, f.deletions) == (1, 1)
    assert [x.text for x in f.lines if x.kind in ("add", "del")] == ["--- old comment", "+++ new comment"]


def test_binary_files_and_no_newline_marker_are_ignored():
    text = "diff --git a/i.png b/i.png\nBinary files a/i.png and b/i.png differ\n"
    assert parse_diff(text)[0].lines == []
    text = MODIFIED + "\\ No newline at end of file\n"
    assert len(parse_diff(text)[0].lines) == 5


def test_renamed_file_uses_the_new_name():
    text = "diff --git a/old.ts b/new.ts\nsimilarity index 90%\nrename from old.ts\nrename to new.ts\n"
    assert parse_diff(text)[0].name == "new.ts"


def test_empty_diff():
    assert parse_diff("") == []
