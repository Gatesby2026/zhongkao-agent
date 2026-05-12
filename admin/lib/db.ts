import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

// 数据库文件放在项目根目录的 data/ 下
const DATA_DIR = path.join(process.cwd(), "..", "data");
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const DB_PATH = path.join(DATA_DIR, "zhongkao.db");

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!_db) {
    _db = new Database(DB_PATH);
    _db.pragma("journal_mode = WAL");
    _db.pragma("foreign_keys = ON");
    initTables(_db);
  }
  return _db;
}

function initTables(db: Database.Database) {
  db.exec(`
    -- 用户表
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      phone VARCHAR(11) UNIQUE NOT NULL,
      nickname VARCHAR(50) DEFAULT '',
      role VARCHAR(20) DEFAULT 'student',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      last_login_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 验证码表
    CREATE TABLE IF NOT EXISTS verification_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      phone VARCHAR(11) NOT NULL,
      code VARCHAR(6) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      expires_at DATETIME NOT NULL,
      used INTEGER DEFAULT 0
    );

    -- 学生画像表
    CREATE TABLE IF NOT EXISTS profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
      district VARCHAR(20) DEFAULT '',
      school VARCHAR(50) DEFAULT '',
      grade VARCHAR(10) DEFAULT '初三',
      current_score INTEGER DEFAULT 0,
      target_school VARCHAR(50) DEFAULT '',
      target_score INTEGER DEFAULT 0,
      hours_per_day REAL DEFAULT 1.5,
      modules_json TEXT DEFAULT '{}',
      knowledge_points_json TEXT DEFAULT '{}',
      preferences_json TEXT DEFAULT '{}',
      completeness INTEGER DEFAULT 0,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 测评记录表
    CREATE TABLE IF NOT EXISTS assessment_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      answers_json TEXT NOT NULL,
      score INTEGER NOT NULL,
      module_results_json TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 刷题记录表
    CREATE TABLE IF NOT EXISTS drill_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      module VARCHAR(50) NOT NULL,
      difficulty VARCHAR(20) DEFAULT 'medium',
      correct_rate REAL DEFAULT 0,
      total_questions INTEGER DEFAULT 0,
      time_spent INTEGER DEFAULT 0,
      details_json TEXT DEFAULT '{}',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 学习计划记录表
    CREATE TABLE IF NOT EXISTS plan_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      plan_text TEXT NOT NULL,
      input_json TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 模考成绩表
    CREATE TABLE IF NOT EXISTS exam_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      exam_name VARCHAR(50) NOT NULL,
      exam_date VARCHAR(20) NOT NULL,
      district VARCHAR(20) DEFAULT '',
      scores_json TEXT NOT NULL,
      total_score INTEGER NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 创建索引
    CREATE INDEX IF NOT EXISTS idx_vc_phone ON verification_codes(phone, expires_at);
    CREATE INDEX IF NOT EXISTS idx_assessment_user ON assessment_records(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_drill_user ON drill_records(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_plan_user ON plan_records(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_exam_user ON exam_records(user_id, created_at);
  `);
}
