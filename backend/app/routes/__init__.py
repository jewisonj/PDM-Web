# API Routes - v2
from .items import router as items_router
from .files import router as files_router
from .bom import router as bom_router
from .projects import router as projects_router
from .auth import router as auth_router
from .tasks import router as tasks_router
from .mrp import router as mrp_router
from .workspace import router as workspace_router
from .nesting import router as nesting_router
from .assistant import router as assistant_router
from .design_books import router as design_books_router
from .kits import router as kits_router
from .design_book_images import router as design_book_images_router

__all__ = [
    "items_router",
    "files_router",
    "bom_router",
    "projects_router",
    "auth_router",
    "tasks_router",
    "mrp_router",
    "workspace_router",
    "nesting_router",
    "assistant_router",
    "design_books_router",
    "kits_router",
    "design_book_images_router",
]
