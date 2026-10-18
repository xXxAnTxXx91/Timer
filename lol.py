import subprocess
import sys
from pathlib import Path


def build_exe():
    project_dir = Path(__file__).resolve().parent
    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)
    spec_path = project_dir / "main_app.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(project_dir / "build"),
        str(spec_path),
    ]
    print("Запуск сборки PyInstaller...")
    result = subprocess.run(cmd)
    print(f"Код завершения: {result.returncode}")
    print(f"Папка с exe: {output_dir}")


if __name__ == "__main__":
    build_exe()
