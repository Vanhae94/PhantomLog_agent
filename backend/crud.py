from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.models import Character
from typing import List, Dict

async def get_all_characters(db: AsyncSession) -> List[Character]:
    """모든 캐릭터 정보 조회"""
    result = await db.execute(select(Character))
    return result.scalars().all()

async def create_character(db: AsyncSession, char_data: Dict):
    """캐릭터 생성"""
    db_char = Character(**char_data)
    db.add(db_char)
    await db.commit()
    await db.refresh(db_char)
    return db_char
