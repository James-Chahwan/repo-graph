use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};

pub struct CliEntrypoint {
    pub from: NodeId,
    pub framework: CliFramework,
    pub command_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CliFramework {
    Click,
    Typer,
    Argparse,
    Cobra,
    Clap,
    Commander,
    Yargs,
    Thor,
    OptionParser,
}

pub fn extract_cli_entrypoints(source: &str, from: NodeId) -> Vec<CliEntrypoint> {
    let mut entries = Vec::new();
    for (pattern, framework) in PATTERNS {
        if source.contains(pattern) {
            entries.push(CliEntrypoint {
                from,
                framework: framework.clone(),
                command_name: pattern.to_string(),
            });
        }
    }
    entries
}

const PATTERNS: &[(&str, CliFramework)] = &[
    ("@click.command", CliFramework::Click),
    ("@click.group", CliFramework::Click),
    ("@app.command", CliFramework::Typer),
    ("typer.Typer", CliFramework::Typer),
    ("argparse.ArgumentParser", CliFramework::Argparse),
    ("cobra.Command", CliFramework::Cobra),
    ("rootCmd", CliFramework::Cobra),
    ("clap::Parser", CliFramework::Clap),
    ("#[command", CliFramework::Clap),
    (".command(", CliFramework::Commander),
    ("yargs(", CliFramework::Yargs),
    ("Thor", CliFramework::Thor),
    ("OptionParser", CliFramework::OptionParser),
];

pub struct CliNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_cli_command_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> CliNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    let extractors: &[fn(&str) -> Option<String>] = &[
        extract_cobra_command_name,
        extract_click_command_name,
        extract_commander_command_name,
        extract_clap_command_name,
    ];
    for line in source.lines() {
        let trimmed = line.trim();
        for extractor in extractors {
            if let Some(name) = extractor(trimmed)
                && seen.insert(name.clone())
            {
                add_cli_command(&mut nodes, &mut nav, &name, module_id, repo);
                break;
            }
        }
    }

    CliNodes { nodes, nav }
}

fn add_cli_command(
    nodes: &mut Vec<Node>,
    nav: &mut CodeNav,
    name: &str,
    module_id: NodeId,
    repo: RepoId,
) {
    let qname = format!("cli:{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::CLI_COMMAND, &qname);
    nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: vec![],
    });
    nav.record(id, name, &qname, node_kind::CLI_COMMAND, Some(module_id));
}

fn extract_cobra_command_name(line: &str) -> Option<String> {
    if !line.contains("cobra.Command") {
        return None;
    }
    let use_idx = line.find("Use:")?;
    let after = &line[use_idx + 4..];
    extract_quoted(after.trim_start())
}

fn extract_click_command_name(line: &str) -> Option<String> {
    let rest = line.strip_prefix("@click.command(")?;
    extract_quoted(rest.trim_start())
}

fn extract_commander_command_name(line: &str) -> Option<String> {
    if !line.contains(".command(") {
        return None;
    }
    let idx = line.find(".command(")?;
    let after = &line[idx + 9..];
    extract_quoted(after.trim_start())
}

fn extract_clap_command_name(line: &str) -> Option<String> {
    if !line.contains("#[command(name") {
        return None;
    }
    let idx = line.find("name")?;
    let after = &line[idx + 4..];
    let eq = after.find('=')?;
    extract_quoted(after[eq + 1..].trim_start())
}

fn extract_quoted(s: &str) -> Option<String> {
    let (quote, rest) = if let Some(rest) = s.strip_prefix('"') {
        ('"', rest)
    } else if let Some(rest) = s.strip_prefix('\'') {
        ('\'', rest)
    } else {
        return None;
    };
    let end = rest.find(quote)?;
    let lit = &rest[..end];
    if lit.is_empty() || lit.len() > 64 {
        return None;
    }
    Some(lit.to_string())
}

const INVOCATION_PATTERNS: &[&str] = &[
    "exec.Command(",
    "exec.CommandContext(",
    "child_process.spawn(",
    "child_process.exec(",
    "child_process.execFile(",
    "execSync(",
    "spawnSync(",
    "subprocess.run(",
    "subprocess.Popen(",
    "subprocess.call(",
    "os.system(",
    "Process.Start(",
    "std::process::Command::new(",
    "Command::new(",
    "system(",
];

pub fn extract_cli_invocation_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> CliNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &pattern in INVOCATION_PATTERNS {
        let mut search_from = 0;
        while let Some(rel_idx) = source[search_from..].find(pattern) {
            let abs = search_from + rel_idx;
            let after = &source[abs + pattern.len()..];
            if let Some(tool) = extract_quoted(after.trim_start())
                && seen.insert(tool.clone())
            {
                let qname = format!("cli_invoke:{tool}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::CLI_INVOCATION, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &tool, &qname, node_kind::CLI_INVOCATION, Some(module_id));
            }
            search_from = abs + pattern.len();
        }
    }

    CliNodes { nodes, nav }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }
    fn module_id() -> NodeId {
        NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test")
    }

    #[test]
    fn detects_click() {
        let id = module_id();
        let refs = extract_cli_entrypoints("@click.command()\ndef run():", id);
        assert!(refs.iter().any(|r| r.framework == CliFramework::Click));
    }

    #[test]
    fn detects_cobra() {
        let id = module_id();
        let refs = extract_cli_entrypoints("var rootCmd = &cobra.Command{}", id);
        assert!(refs.iter().any(|r| r.framework == CliFramework::Cobra));
    }

    #[test]
    fn cobra_command_node() {
        let source = r#"var cmd = &cobra.Command{Use: "migrate"}"#;
        let result = extract_cli_command_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "cli:migrate"));
    }

    #[test]
    fn commander_command_node() {
        let source = "program.command('deploy').description('Deploy app')";
        let result = extract_cli_command_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "cli:deploy"));
    }

    #[test]
    fn detects_exec_command_invocation() {
        let source = "cmd := exec.Command(\"docker\", \"build\", \".\")";
        let result = extract_cli_invocation_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "cli_invoke:docker"));
    }

    #[test]
    fn detects_subprocess_invocation() {
        let _array_form = "subprocess.run(['terraform', 'apply'])";
        let source = "subprocess.run('terraform apply')";
        let result = extract_cli_invocation_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
    }
}
