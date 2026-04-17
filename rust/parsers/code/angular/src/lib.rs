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

pub fn is_angular_file(file_rel_path: &str, source: &str) -> bool {
    file_rel_path.ends_with(".component.ts")
        || file_rel_path.ends_with(".service.ts")
        || file_rel_path.ends_with(".module.ts")
        || file_rel_path.ends_with(".guard.ts")
        || file_rel_path.ends_with(".pipe.ts")
        || file_rel_path.ends_with(".directive.ts")
        || source.contains("@Component")
        || source.contains("@Injectable")
        || source.contains("@NgModule")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }

    #[test]
    fn angular_service() {
        let source = r#"
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class UserService {
  getUsers() {
    return this.http.get('/api/users');
  }
}
"#;
        let fp = parse_file(source, "src/user.service.ts", "src::user.service", repo()).unwrap();
        assert!(fp.nav.name_by_id.values().any(|n| n == "UserService"));
    }

    #[test]
    fn detect_angular() {
        assert!(is_angular_file("src/app.component.ts", ""));
        assert!(is_angular_file("src/foo.ts", "@Component({})"));
        assert!(!is_angular_file("src/foo.ts", "const x = 1;"));
    }
}
