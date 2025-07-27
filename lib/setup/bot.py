import os, re, sys, time, asyncio, subprocess
from concurrent.futures import ThreadPoolExecutor

try:
    import rich
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])

from rich.console import Console
from rich.panel import Panel
from rich.box import ROUNDED
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, TaskProgressColumn, TimeRemainingColumn
)

class SetupManager:
    def __init__(self):
        self.console = Console()
        self.submodule_url = "https://github.com/senko-sleep/Poketwo-AutoNamer.git"
        self.submodule_path = "submodules/poketwo_autonamer"
        self.essential_packages = [
            "urllib3", "pipreqs", "onnxruntime", "discord",
            "opencv-python-headless", "python-Levenshtein",
            "pip", "setuptools", "wheel", "colorthief", "emoji==1.7.0"
        ]
        self.requirements_file = "requirements.txt"
        self.ignore_folders = {"submodules"}
        self.start_time = time.time()
        self.executor = ThreadPoolExecutor(max_workers=16)
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[green bold]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True
        )

    async def run_setup(self):
        with self.progress:
            task1 = self.progress.add_task("Prepare Requirements", total=None)
            await self.prepare_requirements(task1)
            self.progress.remove_task(task1)

            await self._step("Clone Submodule", self.clone_submodule)

            task2 = self.progress.add_task("Install Essentials", total=None)
            await self.install_essentials(task2)
            self.progress.remove_task(task2)

            task3 = self.progress.add_task("Install from Requirements", total=None)
            await self.install_and_update_requirements(task3)
            self.progress.remove_task(task3)

        elapsed = round(time.time() - self.start_time, 2)
        self.console.print(Panel(f"[bold green]Setup completed in {elapsed} seconds.[/bold green]", title="✅ Done", box=ROUNDED))

    async def _step(self, desc, func):
        task = self.progress.add_task(desc, total=None)
        try:
            await func()
        except Exception as e:
            self.console.print(f"[red bold]Error during {desc}: {e}[/red bold]")
        finally:
            self.progress.update(task, completed=1)
            self.progress.remove_task(task)

    async def clone_submodule(self):
        if os.path.exists(self.submodule_path):
            return
        os.makedirs(os.path.dirname(self.submodule_path), exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", self.submodule_url, self.submodule_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()

    async def prepare_requirements(self, task_id):
        self.progress.update(task_id, description="□ Checking requirements.txt...", completed=0)
        if not os.path.exists(self.requirements_file):
            self.progress.update(task_id, description="□ requirements.txt missing, generating...", completed=30)
            retcode = await self.run_cmd_ultra_fast(
                sys.executable, "-m", "pipreqs.pipreqs", "--force", "--ignore",
                "venv,.venv,submodules,node_modules", "."
            )
            if retcode != 0 or not os.path.exists(self.requirements_file):
                self.progress.update(task_id, description="❌ Failed to generate requirements.txt", completed=100)
                return

        self.progress.update(task_id, description="□ Deduplicating requirements...", completed=60)
        with open(self.requirements_file, "r") as f:
            lines = f.readlines()
        deduped = {}
        for line in lines:
            if "==" in line:
                name, version = line.strip().split("==", 1)
                deduped[name] = version
        with open(self.requirements_file, "w") as f:
            for name, version in deduped.items():
                f.write(f"{name}=={version}\n")
        self.progress.update(task_id, description=f"✅ {len(deduped)} packages ready", completed=100)

    async def install_and_update_requirements(self, task_id):
        if not os.path.exists(self.requirements_file):
            self.progress.update(task_id, description="❌ No requirements.txt found", completed=100)
            return

        with open(self.requirements_file) as f:
            reqs = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        to_install = [r for r in reqs if not self._is_package_installed(r)]
        if not to_install:
            self.progress.update(task_id, description="✅ Requirements already satisfied", completed=100)
            return

        self.progress.update(task_id, description=f"□ Installing {len(to_install)} missing packages...", completed=0)
        batch_size = 4
        tasks = []
        for i in range(0, len(to_install), batch_size):
            batch = to_install[i:i+batch_size]
            tasks.append(self._pip_install_batch(batch))
        results = await asyncio.gather(*tasks)
        failed_pkgs = []

        for idx, code in enumerate(results):
            if code != 0:
                failed_pkgs.extend(tasks[idx])

        # After install, update requirements.txt with newly installed packages and versions
        updated_lines = await self.get_installed_package_versions(reqs)
        with open(self.requirements_file, "w") as f:
            for line in updated_lines:
                f.write(line + "\n")

        if all(code == 0 for code in results):
            self.progress.update(task_id, description=f"✅ All missing packages installed and requirements.txt updated", completed=100)
        else:
            self.progress.update(task_id, description=f"⚠️ Some packages failed to install", completed=100)

    async def get_installed_package_versions(self, pkgs):
        try:
            import importlib.metadata as metadata
        except ImportError:
            import importlib_metadata as metadata
        installed_versions = {}
        for dist in metadata.distributions():
            name = dist.metadata["Name"].lower()
            version = dist.version
            installed_versions[name] = version

        lines = []
        for pkg in pkgs:
            name = re.split(r"[<=>]", pkg)[0].strip().lower()
            version = installed_versions.get(name)
            if version:
                lines.append(f"{name}=={version}")
            else:
                lines.append(pkg)  # fallback to original
        return lines

    async def _pip_install_batch(self, packages):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir",
            "--disable-pip-version-check", "--quiet", "--no-warn-script-location",
            *packages,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return proc.returncode

    async def install_essentials(self, task_id):
        to_install = [pkg for pkg in self.essential_packages if not self._is_package_installed(pkg)]
        if not to_install:
            self.progress.update(task_id, description="✅ Essentials already installed", completed=100)
            return
        retcode = await self.run_cmd_ultra_fast(
            sys.executable, "-m", "pip", "install", *to_install,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        if retcode == 0:
            self.progress.update(task_id, description="✅ Essentials installed", completed=100)
        else:
            self.progress.update(task_id, description="❌ Essentials install failed", completed=100)

    def _is_package_installed(self, package: str) -> bool:
        name = re.split(r'[<=>]', package)[0].strip().lower()
        try:
            import importlib.metadata as metadata
        except ImportError:
            import importlib_metadata as metadata
        installed = {dist.metadata["Name"].lower() for dist in metadata.distributions()}
        return name in installed

    async def run_cmd_ultra_fast(self, *args):
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return proc.returncode

def main():
    asyncio.run(SetupManager().run_setup())

if __name__ == "__main__":
    main()
