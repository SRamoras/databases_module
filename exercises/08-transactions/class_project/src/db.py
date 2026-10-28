import os
from dotenv import load_dotenv
from sqlmodel import create_engine

load_dotenv()

public_engine = create_engine(os.environ["PUBLIC_DB_URL"])
private_engine = create_engine(os.environ["PRIVATE_DB_URL"])