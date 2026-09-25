import sqlite3
from typing import List, Tuple, Dict, Any, Optional

DB_NAME = "endocrinologia_avanzada.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Tabla de Pacientes
    c.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            dni TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT NOT NULL
        )
    """)
    
    # Tabla de Controles y Laboratorio
    c.execute("""
        CREATE TABLE IF NOT EXISTS controles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni_paciente TEXT,
            fecha TEXT NOT NULL,
            peso REAL,
            altura REAL,
            hba1c REAL,
            tsh REAL,
            t4l REAL,
            vfg REAL,
            FOREIGN KEY (dni_paciente) REFERENCES pacientes (dni)
        )
    """)
    
    # Tabla de Nódulos Tiroideos
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni_paciente TEXT,
            fecha TEXT NOT NULL,
            localizacion TEXT,
            d1_mm REAL,
            d2_mm REAL,
            d3_mm REAL,
            tirads_score INTEGER,
            FOREIGN KEY (dni_paciente) REFERENCES pacientes (dni)
        )
    """)
    conn.commit()
    conn.close()

def guardar_paciente(dni: str, nombre: str, fecha_nac: str, sexo: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR REPLACE INTO pacientes VALUES (?, ?, ?, ?)",
            (dni, nombre, fecha_nac, sexo)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def obtener_pacientes() -> List[Tuple]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT dni, nombre, fecha_nacimiento, sexo FROM pacientes ORDER BY nombre")
    filas = c.fetchall()
    conn.close()
    return filas

def guardar_control(dni: str, fecha: str, peso: float, altura: float, hba1c: float, tsh: float, t4l: float, vfg: float):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO controles (dni_paciente, fecha, peso, altura, hba1c, tsh, t4l, vfg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (dni, fecha, peso, altura, hba1c, tsh, t4l, vfg))
    conn.commit()
    conn.close()

def obtener_historial_controles(dni: str) -> List[Tuple]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT fecha, peso, hba1c, tsh, t4l, vfg FROM controles WHERE dni_paciente = ? ORDER BY fecha ASC", (dni,))
    filas = c.fetchall()
    conn.close()
    return filas