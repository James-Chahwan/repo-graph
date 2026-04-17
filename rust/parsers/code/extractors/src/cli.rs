use repo_graph_core::NodeId;

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
    ("add_argument", CliFramework::Argparse),
    ("cobra.Command", CliFramework::Cobra),
    ("rootCmd", CliFramework::Cobra),
    ("clap::Parser", CliFramework::Clap),
    ("#[command", CliFramework::Clap),
    (".command(", CliFramework::Commander),
    ("commander", CliFramework::Commander),
    ("yargs(", CliFramework::Yargs),
    (".option(", CliFramework::Yargs),
    ("Thor", CliFramework::Thor),
    ("desc ", CliFramework::Thor),
    ("OptionParser", CliFramework::OptionParser),
];

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_code_domain::{GRAPH_TYPE, node_kind};
    use repo_graph_core::RepoId;

    #[test]
    fn detects_click() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_cli_entrypoints("@click.command()\ndef run():", id);
        assert!(refs.iter().any(|r| r.framework == CliFramework::Click));
    }

    #[test]
    fn detects_cobra() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_cli_entrypoints("var rootCmd = &cobra.Command{}", id);
        assert!(refs.iter().any(|r| r.framework == CliFramework::Cobra));
    }
}
