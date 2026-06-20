// 后端接口封装。dev 下 vite proxy /api → 127.0.0.1:8765

export interface StatusResp {
  id: string; status: string; stage: number;
  stage_name: string; total_stages: number; error: string;
}
export interface ModuleStat {
  name: string; scored: number; full: number; rate: number; lost_qs: string[];
}
export interface WrongQ {
  qid: string; type_cn: string; module_cn: string;
  lost: number; score: number; knowledge_points: string[];
  error_type: string; why_wrong: string[]; fix: string[];
}
export interface ReportResp {
  student_name: string; exam_title: string; subject: string;
  exam_slug: string; total_scored: number; full_score: number;
  rate: number; n_questions: number; n_lost: number; lost_total: number;
  modules: ModuleStat[]; wrong_questions: WrongQ[];
  score_source: 'teacher' | 'auto';
}

export interface TraceQuestion {
  qid: number; final: string; conf: number;
  status: 'green' | 'yellow' | 'red'; reason: string;
  probe: {
    pred: string; margin: number; dens: Record<string, number>;
    cells?: Record<string, [number, number]>; h?: number; page?: string;
  };
  reader: { method: string; pred: string | null; missing: string[] };
  tiebreak: { vlm: string; result: string } | null;
}
export interface ManualChoicesResp {
  id: string; status: string;
  reliability: { reliable?: boolean; reasons?: string[]; need_manual_qids?: number[] };
  current: Record<string, string>;
  recognition_trace: {
    questions?: TraceQuestion[]; aligned?: boolean;
    summary?: { total: number; green: number; yellow: number; red: number; need_review: number[] };
  };
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  async createAnalysis(files: File[]): Promise<{ id: string; status: string }> {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    return j(await fetch('/api/analyses', { method: 'POST', body: fd }))
  },
  async detect(id: string): Promise<{
    id: string; status: string; error: string;
    detected: {
      exam_slug?: string; exam_title?: string; district?: string;
      subject?: string; year?: string; exam_type?: string;
      student_name?: string; student_id?: string;
      pages_complete?: boolean; completeness_note?: string;
      matched?: boolean;
      precheck?: { block: boolean; hard: string[]; warn: string[] };
    }
  }> {
    return j(await fetch(`/api/analyses/${id}/detect`))
  },
  async startPipeline(id: string, studentName?: string) {
    const qs = studentName ? `?student_name=${encodeURIComponent(studentName)}` : ''
    return j(await fetch(`/api/analyses/${id}/start${qs}`, { method: 'POST' }))
  },
  async uploadScores(id: string, file: File) {
    const fd = new FormData()
    fd.append('file', file)
    return j(await fetch(`/api/analyses/${id}/scores`, { method: 'POST', body: fd }))
  },
  async status(id: string): Promise<StatusResp> {
    return j(await fetch(`/api/analyses/${id}/status`))
  },
  async getManualChoices(id: string): Promise<ManualChoicesResp> {
    return j(await fetch(`/api/analyses/${id}/manual-choices`))
  },
  async submitManualChoices(id: string, choices: Record<string, string>) {
    return j(await fetch(`/api/analyses/${id}/manual-choices`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ choices }),
    }))
  },
  async report(id: string): Promise<ReportResp> {
    return j(await fetch(`/api/analyses/${id}/report`))
  },
  reportPdfUrl(id: string) { return `/api/analyses/${id}/report.pdf` },
  paperPdfUrl(id: string) { return `/api/analyses/${id}/paper.pdf` },
  async list(): Promise<{ items: Array<{
    id: string; student_name: string; exam_slug: string;
    status: string; created_at: number;
  }> }> {
    return j(await fetch('/api/analyses'))
  },
  async coverage(): Promise<{
    city: string;
    total_papers: number;
    subjects: Array<{
      subject_cn: string; subject_en: string;
      by_exam_type: Array<{
        exam_type_cn: string; exam_type_en: string;
        n_districts: number; districts: string[]; years: string[];
      }>;
    }>;
  }> {
    return j(await fetch('/api/coverage'))
  },
}
