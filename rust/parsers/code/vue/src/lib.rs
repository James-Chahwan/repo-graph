pub use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, GRAPH_TYPE, ImportStmt, ImportTarget, ParseError,
    UnresolvedRef, cell_type, edge_category, node_kind,
};
use repo_graph_core::RepoId;

pub fn parse_file(
    source: &str,
    file_rel_path: &str,
    module_qname: &str,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let script = extract_script(source);
    repo_graph_parser_typescript::parse_file(script, file_rel_path, module_qname, repo)
}

fn extract_script(source: &str) -> &str {
    if let Some(start) = source.find("<script")
        && let Some(tag_end) = source[start..].find('>')
    {
        let content_start = start + tag_end + 1;
        if let Some(end) = source[content_start..].find("</script>") {
            return &source[content_start..content_start + end];
        }
    }
    source
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }

    #[test]
    fn vue_sfc() {
        let source = r#"
<template>
  <div>{{ message }}</div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const message = ref('Hello');

function greet() {
  console.log(message.value);
}
</script>
"#;
        let fp = parse_file(source, "src/App.vue", "src::App", repo()).unwrap();
        assert!(fp.nav.name_by_id.values().any(|n| n == "greet"));
    }

    #[test]
    fn plain_ts_fallback() {
        let source = r#"
export function helper() {
  return 42;
}
"#;
        let fp = parse_file(source, "src/util.ts", "src::util", repo()).unwrap();
        assert!(fp.nav.name_by_id.values().any(|n| n == "helper"));
    }

    #[test]
    fn extract_script_section() {
        let sfc = r#"<template><div/></template>
<script>const x = 1;</script>"#;
        assert_eq!(extract_script(sfc), "const x = 1;");
    }
}
