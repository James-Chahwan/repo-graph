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
    repo_graph_parser_typescript::parse_file(source, file_rel_path, module_qname, repo)
}

pub fn is_react_file(source: &str) -> bool {
    source.contains("from 'react'")
        || source.contains("from \"react\"")
        || source.contains("from 'react-")
        || source.contains("require('react')")
        || source.contains("useState")
        || source.contains("useEffect")
        || source.contains("</>")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }

    #[test]
    fn react_component() {
        let source = r#"
import React from 'react';

function App() {
  return <div>Hello</div>;
}

export default App;
"#;
        let fp = parse_file(source, "src/App.tsx", "src::App", repo()).unwrap();
        assert!(fp.nav.name_by_id.values().any(|n| n == "App"));
    }

    #[test]
    fn detect_react() {
        assert!(is_react_file("import { useState } from 'react';"));
        assert!(!is_react_file("const x = 1;"));
    }
}
