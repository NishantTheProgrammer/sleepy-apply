from abc import ABC, abstractmethod


class BaseResumeTemplate(ABC):
    name: str = "base"

    @abstractmethod
    def render_pdf(self, content: dict, output_path: str) -> str:
        """Render a PDF resume to output_path and return the path."""
        pass
