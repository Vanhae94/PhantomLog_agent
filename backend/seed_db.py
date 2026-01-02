import asyncio
from backend.database import AsyncSessionLocal
from backend.crud import get_all_characters, create_character
from characters import student, office_worker, artist, chef, teacher

async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Checking existing characters...")
        characters = await get_all_characters(db)
        if not characters:
            print("Creating initial character data...")
            character_modules = [student, office_worker, artist, chef, teacher]
            for module in character_modules:
                char_info = module.get_character_info()
                # Remove keys not in model
                char_info_clean = {k: v for k, v in char_info.items() if k != 'age'}
                await create_character(db, char_info_clean)
                print(f"Created: {char_info['name']}")
            print("Seeding complete.")
        else:
            print(f"Database already has {len(characters)} characters.")

if __name__ == "__main__":
    asyncio.run(seed_data())
