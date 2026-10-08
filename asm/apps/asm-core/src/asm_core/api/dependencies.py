"""FastAPI dependencies shared across the routers."""

from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_core.db.database import get_session

Session = Annotated[AsyncSession, Depends(get_session)]
