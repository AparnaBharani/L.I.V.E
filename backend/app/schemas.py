from pydantic import BaseModel, ConfigDict

class ExperienceBase(BaseModel):
    title: str
    description: str
    category: str
    difficulty: str
    duration_minutes: int
    cost: int = 0

class ExperienceCreate(ExperienceBase):
    pass

class ExperienceResponse(ExperienceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
