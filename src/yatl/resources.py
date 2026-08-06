from abc import ABC, abstractmethod
from pathlib import Path
import sysconfig


class ResourceLocator(ABC):
    """Locates YATL runtime resources."""

    @property
    @abstractmethod
    def root(self) -> Path:
        ...

    @property
    def schema_dir(self) -> Path:
        return self.root / "schema"

    @property
    def static_dir(self) -> Path:
        return self.root / "static"

    @property
    def template_dir(self) -> Path:
        return self.root / "templates"


class RepositoryResourceLocator(ResourceLocator):
    """Resources are loaded directly from a source checkout."""

    def __init__(self, repository_root: Path):
        self._root = repository_root.resolve()

    def root(self) -> Path:
        return self._root


class InstalledResourceLocator(ResourceLocator):
    """Resources are loaded from an installed application."""

    def __init__(self):
        self._root = Path(sysconfig.get_path("data")) / "share" / "yatl"

    def root(self) -> Path:
        return self._root
