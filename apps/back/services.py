from sqlmodel import Session, select
from models import movieTitle, chapterContent, character, altCharacter, entity, altEntity

def merge_tags(old_tags: str, new_tags: str) -> str:
    """Helper function to merge comma-separated tags and remove duplicates."""
    if not old_tags:
        return new_tags
    if not new_tags:
        return old_tags
    
    s1 = set(t.strip() for t in old_tags.split(',') if t.strip())
    s2 = set(t.strip() for t in new_tags.split(',') if t.strip())
    merged = s1.union(s2)
    return ", ".join(sorted(list(merged)))

def save_extraction_result(session: Session, chapter_id: int, data: dict):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter or not chapter.movieId:
        print("Error: Chapter not found or not linked to a movie.")
        return False
    
    current_movie_id = chapter.movieId
    for char_data in data.get("characters", []):
        name = char_data["name"]
        statement = select(character).where(
            character.name == name, 
            character.movieId == current_movie_id
        )
        existing_char = session.exec(statement).first()

        if existing_char:
            existing_char.IdentityTags = merge_tags(existing_char.IdentityTags, char_data.get("IdentityTags", ""))
            existing_char.ModifierTags = merge_tags(existing_char.ModifierTags, char_data.get("ModifierTags", ""))
            session.add(existing_char)
            target_char_id = existing_char.id
        else:
            new_char = character(
                name=name,
                type="Character",
                IdentityTags=char_data.get("IdentityTags", ""),
                ModifierTags=char_data.get("ModifierTags", ""),
                movieId=current_movie_id
            )
            session.add(new_char)
            session.commit()
            session.refresh(new_char)
            target_char_id = new_char.id

        if "altNames" in char_data:
            for alt in char_data["altNames"]:
                alt_stmt = select(altCharacter).where(
                    altCharacter.altName == alt,
                    altCharacter.entityId == target_char_id
                )
                if not session.exec(alt_stmt).first():
                    session.add(altCharacter(altName=alt, entityId=target_char_id))

    all_general_entities = data.get("locations", []) + data.get("items", [])

    for ent_data in all_general_entities:
        name = ent_data["name"]
        e_type = ent_data["type"]

        statement = select(entity).where(
            entity.name == name,
            entity.type == e_type,
            entity.movieId == current_movie_id
        )
        existing_ent = session.exec(statement).first()

        if existing_ent:
            existing_ent.visual_tags = merge_tags(existing_ent.visual_tags, ent_data.get("VisualTags", ""))
            session.add(existing_ent)
            target_ent_id = existing_ent.id
        else:
            new_ent = entity(
                name=name,
                type=e_type,
                visual_tags=ent_data.get("VisualTags", ""),
                movieId=current_movie_id
            )
            session.add(new_ent)
            session.commit()
            session.refresh(new_ent)
            target_ent_id = new_ent.id
        if "altNames" in ent_data:
            for alt in ent_data["altNames"]:
                alt_stmt = select(altEntity).where(
                    altEntity.altName == alt,
                    altEntity.entityId == target_ent_id
                )
                if not session.exec(alt_stmt).first():
                    session.add(altEntity(altName=alt, entityId=target_ent_id))
    chapter.isExtracted = True
    session.add(chapter)

    session.commit()
    return True