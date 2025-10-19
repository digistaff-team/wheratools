from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime
from typing import Optional
from models import SessionLocal, CrewMember, Tool, ToolAssignment, RepairRecord, CurrentAssignment



app = FastAPI(title="Tool Tracker API", version="2.0")

# CORS для frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_frontend():
    """Главная страница с веб-интерфейсом"""
    return FileResponse("static/index.html")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ToolStatusResponse(BaseModel):
    tool_id: int
    tool_name: str
    current_holder: Optional[str] = None
    assigned_at: Optional[datetime.datetime] = None
    status: str
    last_check_status: Optional[bool] = None
    last_check_date: Optional[datetime.datetime] = None
    repair_info: Optional[dict] = None

class AssignRequest(BaseModel):
    tool_id: int
    member_id: int

class ReturnRequest(BaseModel):
    tool_id: int
    checked_by: str
    is_working: bool
    condition_notes: Optional[str] = ""
    issue_description: Optional[str] = ""

class StartRepairRequest(BaseModel):
    repair_id: int
    repaired_by: str

class CompleteRepairRequest(BaseModel):
    repair_id: int
    repair_notes: str
    is_fixed: bool

@app.get("/")
def root():
    return {"message": "Tool Tracker API v2.0 with PostgreSQL/Supabase", "status": "running"}

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Проверка здоровья API и подключения к БД"""
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/tools/status")
async def get_tools_status():
    """Получить статус всех инструментов"""
    db = SessionLocal()
    try:
        # Получаем все инструменты
        tools = db.query(Tool).all()
        
        result = []
        for tool in tools:
            # Проверяем есть ли активная выдача
            current_assignment = db.query(CurrentAssignment).filter(
                CurrentAssignment.tool_id == tool.id
            ).first()
            
            # Проверяем есть ли активный ремонт
            active_repair = db.query(RepairRecord).filter(
                RepairRecord.tool_id == tool.id,
                RepairRecord.status.in_(['reported', 'in_progress'])
            ).first()
            
            # Определяем статус
            if active_repair:
                status = "in_repair"
                current_holder = None
                repair_info = {
                    "issue": active_repair.issue,
                    "reported_at": str(active_repair.reported_at) if active_repair.reported_at else None
                }
            elif current_assignment:
                status = "assigned"
                member = db.query(CrewMember).filter(
                    CrewMember.id == current_assignment.member_id
                ).first()
                current_holder = member.name if member else None
                repair_info = None
            else:
                status = "available"
                current_holder = None
                repair_info = None
            
            result.append({
                "tool_id": tool.id,
                "tool_name": tool.name,
                "status": status,
                "current_holder": current_holder,
                "repair_info": repair_info
            })
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        db.close()

    
    return result

@app.get("/members")
def get_members(db: Session = Depends(get_db)):
    """Получить список всех членов бригады"""
    members = db.query(CrewMember).all()
    return [{"id": m.id, "name": m.name} for m in members]

@app.post("/tools/assign")
def assign_tool(request: AssignRequest, db: Session = Depends(get_db)):
    """Выдать инструмент работнику"""
    assignment = db.query(CurrentAssignment).filter_by(
        tool_id=request.tool_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    
    if assignment.member_id is not None:
        raise HTTPException(
            status_code=400, 
            detail="Инструмент уже выдан другому работнику"
        )
    
    if assignment.last_check_status is False:
        raise HTTPException(
            status_code=400,
            detail="Инструмент неисправен и не может быть выдан"
        )
    
    assignment.member_id = request.member_id
    assignment.assigned_at = datetime.datetime.utcnow()
    assignment.status = "assigned"
    
    db.add(ToolAssignment(
        tool_id=request.tool_id,
        member_id=request.member_id,
        action="assign",
        timestamp=datetime.datetime.utcnow()
    ))
    
    db.commit()
    return {"success": True, "message": "Инструмент успешно выдан"}

@app.post("/tools/return")
def return_tool(request: ReturnRequest, db: Session = Depends(get_db)):
    """Возврат инструмента с проверкой"""
    assignment = db.query(CurrentAssignment).filter_by(
        tool_id=request.tool_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    
    if assignment.member_id is None:
        raise HTTPException(
            status_code=400,
            detail="Инструмент уже находится в инвентаре"
        )
    
    if assignment.status == "in_repair":
        raise HTTPException(
            status_code=400,
            detail="Инструмент находится в ремонте"
        )
    
    returning_member_id = assignment.member_id
    check_timestamp = datetime.datetime.utcnow()
    
    if request.is_working:
        db.add(ToolAssignment(
            tool_id=request.tool_id,
            member_id=returning_member_id,
            action="return",
            timestamp=check_timestamp,
            is_checked=True,
            checked_by=request.checked_by,
            condition_notes=request.condition_notes,
            checked_at=check_timestamp
        ))
        
        assignment.member_id = None
        assignment.assigned_at = None
        assignment.status = "available"
        assignment.last_check_status = True
        assignment.last_check_date = check_timestamp
        assignment.repair_id = None
        
        db.commit()
        
        return {
            "success": True,
            "message": "Инструмент возвращён в инвентарь",
            "status": "available"
        }
    else:
        if not request.issue_description:
            raise HTTPException(
                status_code=400,
                detail="Необходимо указать описание неисправности"
            )
        
        repair = RepairRecord(
            tool_id=request.tool_id,
            member_id=returning_member_id,
            reported_by=request.checked_by,
            issue_description=request.issue_description,
            reported_at=check_timestamp,
            status="pending"
        )
        db.add(repair)
        db.flush()
        
        db.add(ToolAssignment(
            tool_id=request.tool_id,
            member_id=returning_member_id,
            action="repair_reported",
            timestamp=check_timestamp,
            is_checked=True,
            checked_by=request.checked_by,
            condition_notes=f"НЕИСПРАВЕН: {request.issue_description}",
            checked_at=check_timestamp
        ))
        
        assignment.status = "in_repair"
        assignment.last_check_status = False
        assignment.last_check_date = check_timestamp
        assignment.repair_id = repair.id
        
        db.commit()
        
        member = db.query(CrewMember).filter_by(id=returning_member_id).first()
        
        return {
            "success": True,
            "message": f"Выявлена неисправность. Инструмент переведён в статус 'В РЕМОНТЕ' и остаётся у {member.name}",
            "status": "in_repair",
            "repair_id": repair.id,
            "issue": request.issue_description,
            "held_by": member.name
        }

@app.post("/repairs/start")
def start_repair(request: StartRepairRequest, db: Session = Depends(get_db)):
    """Начать ремонт"""
    repair = db.query(RepairRecord).filter_by(id=request.repair_id).first()
    
    if not repair:
        raise HTTPException(status_code=404, detail="Запись о ремонте не найдена")
    
    if repair.status != "pending":
        raise HTTPException(status_code=400, detail="Ремонт уже начат или завершён")
    
    repair.status = "in_progress"
    repair.repair_started_at = datetime.datetime.utcnow()
    repair.repaired_by = request.repaired_by
    
    db.commit()
    
    return {"success": True, "message": f"Ремонт начат мастером {request.repaired_by}"}

@app.post("/repairs/complete")
def complete_repair(request: CompleteRepairRequest, db: Session = Depends(get_db)):
    """Завершить ремонт"""
    repair = db.query(RepairRecord).filter_by(id=request.repair_id).first()
    
    if not repair:
        raise HTTPException(status_code=404, detail="Запись о ремонте не найдена")
    
    if repair.status == "completed":
        raise HTTPException(status_code=400, detail="Ремонт уже завершён")
    
    completion_time = datetime.datetime.utcnow()
    
    repair.status = "completed"
    repair.repair_completed_at = completion_time
    repair.repair_notes = request.repair_notes
    
    db.add(ToolAssignment(
        tool_id=repair.tool_id,
        member_id=repair.member_id,
        action="repair_completed",
        timestamp=completion_time,
        is_checked=True,
        checked_by=repair.repaired_by,
        condition_notes=f"Ремонт завершён. {request.repair_notes}",
        checked_at=completion_time
    ))
    
    assignment = db.query(CurrentAssignment).filter_by(tool_id=repair.tool_id).first()
    
    if request.is_fixed:
        assignment.status = "available"
        assignment.member_id = None
        assignment.assigned_at = None
        assignment.last_check_status = True
        assignment.last_check_date = completion_time
        assignment.repair_id = None
        message = "Ремонт завершён. Инструмент возвращён в инвентарь и готов к выдаче"
    else:
        message = "Ремонт завершён, но инструмент не исправен"
    
    db.commit()
    
    return {"success": True, "message": message, "is_fixed": request.is_fixed, "status": assignment.status}

@app.get("/repairs/active")
def get_active_repairs(db: Session = Depends(get_db)):
    """Получить список активных ремонтов"""
    repairs = db.query(RepairRecord).filter(
        RepairRecord.status.in_(["pending", "in_progress"])
    ).all()
    
    result = []
    for r in repairs:
        member = db.query(CrewMember).filter_by(id=r.member_id).first()
        result.append({
            "repair_id": r.id,
            "tool": r.tool.name,
            "issue": r.issue_description,
            "reported_by": r.reported_by,
            "reported_at": r.reported_at.isoformat() if r.reported_at else None,
            "held_by": member.name if member else None,
            "status": r.status,
            "repaired_by": r.repaired_by,
            "started_at": r.repair_started_at.isoformat() if r.repair_started_at else None
        })
    
@app.post("/init-database")
async def init_database():
    """Создание всех таблиц в базе данных"""
    try:
        from models import Base, engine
        Base.metadata.create_all(bind=engine)
        
        db = SessionLocal()
        try:
            # Проверяем есть ли уже данные
            existing_members = db.query(CrewMember).count()
            existing_tools = db.query(Tool).count()
            
            if existing_members == 0:
                members = [
                    CrewMember(name="Василий Петров"),
                    CrewMember(name="Иван Сидоров"), 
                    CrewMember(name="Пётр Иванов")
                ]
                for member in members:
                    db.add(member)
            
            if existing_tools == 0:
                tools = [
                    Tool(name="электролобзик"),
                    Tool(name="бетономешалка"),
                    Tool(name="перфоратор")
                ]
                for tool in tools:
                    db.add(tool)
            
            db.commit()
            
            return {
                "message": "База данных успешно инициализирована",
                "tables_created": True,
                "members_added": existing_members == 0,
                "tools_added": existing_tools == 0
            }
            
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
        finally:
            db.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании таблиц: {str(e)}")

@app.post("/force-add-data")
async def force_add_data():
    """Принудительное добавление тестовых данных (очистка и пересоздание)"""
    db = SessionLocal()
    try:
        # Очищаем все таблицы в правильном порядке (из-за foreign keys)
        db.query(CurrentAssignment).delete()
        db.query(ToolAssignment).delete()
        db.query(RepairRecord).delete()
        db.query(Tool).delete()
        db.query(CrewMember).delete()
        db.commit()
        
        # Добавляем работников
        members_data = ["Василий Петров", "Иван Сидоров", "Пётр Иванов"]
        members = []
        for name in members_data:
            member = CrewMember(name=name)
            db.add(member)
            members.append(member)
        db.commit()
        
        # Добавляем инструменты
        tools_data = ["электролобзик", "бетономешалка", "перфоратор"]
        tools = []
        for name in tools_data:
            tool = Tool(name=name)
            db.add(tool)
            tools.append(tool)
        db.commit()
        
        # Проверяем что данные действительно добавились
        members_count = db.query(CrewMember).count()
        tools_count = db.query(Tool).count()
        
        return {
            "message": "Данные успешно добавлены",
            "members_added": members_count,
            "tools_added": tools_count,
            "members_list": [m.name for m in members],
            "tools_list": [t.name for t in tools]
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
    finally:
        db.close()

@app.get("/debug-tools")
async def debug_tools():
    """Отладочный endpoint для проверки данных"""
    db = SessionLocal()
    try:
        # Проверяем просто все инструменты
        tools = db.query(Tool).all()
        members = db.query(CrewMember).all()
        assignments = db.query(CurrentAssignment).all()
        
        tools_data = []
        for tool in tools:
            tools_data.append({
                "id": tool.id,
                "name": tool.name,
                "created_at": str(tool.created_at) if tool.created_at else None
            })
        
        members_data = []
        for member in members:
            members_data.append({
                "id": member.id,
                "name": member.name
            })
        
        return {
            "tools_count": len(tools),
            "members_count": len(members),
            "assignments_count": len(assignments),
            "tools": tools_data,
            "members": members_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
    finally:
        db.close()


    return result
