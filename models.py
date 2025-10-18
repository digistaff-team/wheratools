from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Подключение к PostgreSQL на Supabase
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class CrewMember(Base):
    __tablename__ = "crew_member"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Tool(Base):
    __tablename__ = "tool"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ToolAssignment(Base):
    __tablename__ = "tool_assignment"
    id = Column(Integer, primary_key=True)
    tool_id = Column(Integer, ForeignKey("tool.id", ondelete="CASCADE"))
    member_id = Column(Integer, ForeignKey("crew_member.id", ondelete="CASCADE"))
    action = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    is_checked = Column(Boolean, nullable=True)
    checked_by = Column(String(255), nullable=True)
    condition_notes = Column(Text, nullable=True)
    checked_at = Column(DateTime, nullable=True)
    
    tool = relationship("Tool")
    member = relationship("CrewMember")

class RepairRecord(Base):
    __tablename__ = "repair_record"
    id = Column(Integer, primary_key=True)
    tool_id = Column(Integer, ForeignKey("tool.id", ondelete="CASCADE"))
    member_id = Column(Integer, ForeignKey("crew_member.id", ondelete="CASCADE"))
    reported_by = Column(String(255), nullable=False)
    issue_description = Column(Text, nullable=False)
    reported_at = Column(DateTime, default=datetime.datetime.utcnow)
    repair_started_at = Column(DateTime, nullable=True)
    repair_completed_at = Column(DateTime, nullable=True)
    repaired_by = Column(String(255), nullable=True)
    repair_notes = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    
    tool = relationship("Tool")
    member = relationship("CrewMember")

class CurrentAssignment(Base):
    __tablename__ = "current_assignment"
    id = Column(Integer, primary_key=True)
    tool_id = Column(Integer, ForeignKey("tool.id", ondelete="CASCADE"), unique=True)
    member_id = Column(Integer, ForeignKey("crew_member.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    last_check_status = Column(Boolean, nullable=True)
    last_check_date = Column(DateTime, nullable=True)
    status = Column(String(50), default="available")
    repair_id = Column(Integer, ForeignKey("repair_record.id", ondelete="SET NULL"), nullable=True)
    
    tool = relationship("Tool")
    member = relationship("CrewMember")
    repair = relationship("RepairRecord")
 
