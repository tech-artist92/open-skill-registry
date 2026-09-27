from typer.testing import CliRunner

from open_skill_registry.cli.main import app

runner = CliRunner()

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Open Skill Registry version:" in result.stdout

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "serve" in result.stdout

def test_init_embedded_mode(tmp_path):
    output_file = tmp_path / "osr.config.yaml"
    result = runner.invoke(app, ["init", "--output", str(output_file)])
    assert result.exit_code == 0
    assert output_file.exists()
    content = output_file.read_text()
    assert "mode: embedded" in content
    assert "fastembed" in content

def test_init_server_mode(tmp_path):
    output_file = tmp_path / "osr.config.yaml"
    result = runner.invoke(app, ["init", "--mode", "server", "--output", str(output_file)])
    assert result.exit_code == 0
    assert output_file.exists()
    content = output_file.read_text()
    assert "mode: server" in content

def test_init_force(tmp_path):
    output_file = tmp_path / "osr.config.yaml"
    output_file.write_text("dummy")
    
    # Without force, non-interactive should fail or prompt. In test, we expect failure or skip.
    result_no_force = runner.invoke(app, ["init", "--output", str(output_file)])
    assert result_no_force.exit_code != 0
    
    # With force
    result_force = runner.invoke(app, ["init", "--output", str(output_file), "--force"])
    assert result_force.exit_code == 0
    assert "mode: embedded" in output_file.read_text()

def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.stdout
