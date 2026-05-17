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
    }
  }> {
    return j(await fetch(`/api/analyses/${id}/detect`))
  },
  async startPipeline(id: string) {
    return j(await fetch(`/api/analyses/${id}/start`, { method: 'POST' }))
  },
  async uploadScores(id: string, file: File) {
    const fd = new FormData()
    fd.append('file', file)
    return j(await fetch(`/api/analyses/${id}/scores`, { method: 'POST', body: fd }))
  },
  async status(id: string): Promise<StatusResp> {
    return j(await fetch(`/api/analyses/${id}/status`))
  },
  async report(id: string): Promise<ReportResp> {
    return j(await fetch(`/api/analyses/${id}/report`))
  },
  reportPdfUrl(id: string) { return `/api/analyses/${id}/report.pdf` },
  paperPdfUrl(id: string) { return `/api/analyses/${id}/paper.pdf` },
}
