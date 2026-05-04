import React, { useState, useEffect } from 'react';
import { Upload, FileText, X, Loader2, Download, ChevronDown, ChevronUp, Briefcase, Users, Sparkles, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';

export default function CVShortlister() {
  const [jdMode, setJdMode] = useState('paste');
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState(null);

  const [cvs, setCvs] = useState([]);
  const [cvMode, setCvMode] = useState('upload');
  const [pasteName, setPasteName] = useState('');
  const [pasteText, setPasteText] = useState('');

  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [results, setResults] = useState([]);
  const [expanded, setExpanded] = useState(new Set());
  const [error, setError] = useState('');

  const [pdfReady, setPdfReady] = useState(false);

  useEffect(() => {
    if (window.pdfjsLib) { setPdfReady(true); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    s.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      setPdfReady(true);
    };
    document.body.appendChild(s);
  }, []);

  const extractPdfText = async (file) => {
    const buf = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: buf }).promise;
    let text = '';
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      text += content.items.map(it => it.str).join(' ') + '\n';
    }
    return text.trim();
  };

  const handleJdUpload = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setError('');
    try {
      const t = await extractPdfText(f);
      setJdText(t);
      setJdFile(f);
    } catch (err) {
      setError('Failed to read JD PDF: ' + err.message);
    }
  };

  const handleCvUpload = async (e) => {
    const files = Array.from(e.target.files);
    setError('');
    for (const f of files) {
      try {
        const t = await extractPdfText(f);
        const name = f.name.replace(/\.pdf$/i, '');
        setCvs(prev => [...prev, { id: Date.now() + Math.random(), name, text: t }]);
      } catch (err) {
        setError(`Failed to read ${f.name}: ${err.message}`);
      }
    }
    e.target.value = '';
  };

  const addPastedCv = () => {
    if (!pasteName.trim() || !pasteText.trim()) return;
    setCvs(prev => [...prev, {
      id: Date.now() + Math.random(),
      name: pasteName.trim(),
      text: pasteText.trim()
    }]);
    setPasteName('');
    setPasteText('');
  };

  const removeCv = (id) => setCvs(prev => prev.filter(c => c.id !== id));
  const updateCvName = (id, name) => setCvs(prev => prev.map(c => c.id === id ? { ...c, name } : c));

  const analyzeCv = async (cv, jd) => {
    const prompt = `You are an expert recruiter. Analyze this candidate's CV against the job description and provide a matching assessment.

JOB DESCRIPTION:
${jd}

CANDIDATE CV:
${cv.text}

Evaluate based on:
- Required skills match
- Years and relevance of experience
- Education/qualifications fit
- Domain expertise
- Notable strengths beyond requirements

Respond with ONLY valid JSON, no markdown fences, no preamble. Use this exact structure:
{"score": <integer 0-100>, "strengths": ["...", "..."], "gaps": ["...", "..."]}

The score should reflect overall fit (0=no match, 100=perfect match). Provide 3-5 specific strengths and 2-4 specific gaps. Be concrete - reference actual skills, experiences, or requirements.`;

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 1000,
        messages: [{ role: "user", content: prompt }]
      })
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`API ${res.status}: ${errText.slice(0, 100)}`);
    }

    const data = await res.json();
    const text = data.content.map(c => c.text || '').join('').trim();
    const clean = text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    return {
      score: Math.max(0, Math.min(100, parseInt(parsed.score) || 0)),
      strengths: Array.isArray(parsed.strengths) ? parsed.strengths : [],
      gaps: Array.isArray(parsed.gaps) ? parsed.gaps : []
    };
  };

  const runAnalysis = async () => {
    if (!jdText.trim()) { setError('Please provide a job description'); return; }
    if (cvs.length === 0) { setError('Please add at least one CV'); return; }

    setError('');
    setAnalyzing(true);
    setResults([]);
    setExpanded(new Set());
    setProgress({ current: 0, total: cvs.length });

    const out = [];
    for (let i = 0; i < cvs.length; i++) {
      const cv = cvs[i];
      try {
        const a = await analyzeCv(cv, jdText);
        out.push({ id: cv.id, name: cv.name, score: a.score, strengths: a.strengths, gaps: a.gaps });
      } catch (err) {
        out.push({ id: cv.id, name: cv.name, score: 0, strengths: [], gaps: [], error: err.message });
      }
      setProgress({ current: i + 1, total: cvs.length });
      setResults([...out].sort((a, b) => b.score - a.score));
    }

    setAnalyzing(false);
  };

  const toggleExpand = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const downloadCsv = () => {
    const rows = [
      ['Rank', 'Name', 'Match Score (%)', 'Strengths', 'Gaps'],
      ...results.map((r, i) => [i + 1, r.name, r.score, r.strengths.join('; '), r.gaps.join('; ')])
    ];
    const csv = rows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cv-shortlist.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const scoreColor = (s) => s >= 80 ? 'bg-emerald-500' : s >= 60 ? 'bg-amber-500' : s >= 40 ? 'bg-orange-500' : 'bg-red-500';
  const scoreText = (s) => s >= 80 ? 'text-emerald-700' : s >= 60 ? 'text-amber-700' : s >= 40 ? 'text-orange-700' : 'text-red-700';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-4 md:p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 mb-3 px-3 py-1 bg-white rounded-full shadow-sm border border-slate-200">
            <Sparkles className="w-4 h-4 text-blue-600" />
            <span className="text-sm font-medium text-slate-700">AI-Powered Shortlisting</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-slate-900 mb-2">CV Shortlisting Tool</h1>
          <p className="text-slate-600">Match candidates to your job description with AI scoring</p>
        </div>

        <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
              <Briefcase className="w-4 h-4 text-blue-600" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Step 1 — Job Description</h2>
          </div>

          <div className="flex gap-2 mb-3">
            <button onClick={() => setJdMode('paste')} className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${jdMode === 'paste' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>Paste Text</button>
            <button onClick={() => setJdMode('upload')} className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${jdMode === 'upload' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>Upload PDF</button>
          </div>

          {jdMode === 'paste' ? (
            <textarea
              value={jdText}
              onChange={(e) => { setJdText(e.target.value); setJdFile(null); }}
              placeholder="Paste the job description here..."
              className="w-full h-40 p-3 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            />
          ) : (
            <label className="flex flex-col items-center justify-center h-40 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-blue-500 hover:bg-blue-50 transition">
              <input type="file" accept="application/pdf" onChange={handleJdUpload} className="hidden" disabled={!pdfReady} />
              {jdFile ? (
                <>
                  <FileText className="w-8 h-8 text-blue-600 mb-2" />
                  <span className="text-sm font-medium text-slate-700">{jdFile.name}</span>
                  <span className="text-xs text-slate-500 mt-1">{jdText.length} chars extracted • Click to replace</span>
                </>
              ) : (
                <>
                  <Upload className="w-8 h-8 text-slate-400 mb-2" />
                  <span className="text-sm font-medium text-slate-700">{pdfReady ? 'Click to upload JD PDF' : 'Loading PDF reader...'}</span>
                  <span className="text-xs text-slate-500 mt-1">PDF only</span>
                </>
              )}
            </label>
          )}
        </section>

        <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center">
                <Users className="w-4 h-4 text-purple-600" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Step 2 — Candidate CVs</h2>
            </div>
            <span className="text-sm text-slate-500">{cvs.length} added</span>
          </div>

          <div className="flex gap-2 mb-3">
            <button onClick={() => setCvMode('upload')} className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${cvMode === 'upload' ? 'bg-purple-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>Upload PDFs</button>
            <button onClick={() => setCvMode('paste')} className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${cvMode === 'paste' ? 'bg-purple-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>Paste Text</button>
          </div>

          {cvMode === 'upload' ? (
            <label className="flex flex-col items-center justify-center h-32 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-purple-500 hover:bg-purple-50 transition">
              <input type="file" accept="application/pdf" multiple onChange={handleCvUpload} className="hidden" disabled={!pdfReady} />
              <Upload className="w-7 h-7 text-slate-400 mb-2" />
              <span className="text-sm font-medium text-slate-700">{pdfReady ? 'Click to upload CV PDFs (multiple allowed)' : 'Loading PDF reader...'}</span>
              <span className="text-xs text-slate-500 mt-1">Filename will be used as candidate name</span>
            </label>
          ) : (
            <div className="space-y-2">
              <input type="text" value={pasteName} onChange={(e) => setPasteName(e.target.value)} placeholder="Candidate name" className="w-full p-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent" />
              <textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)} placeholder="Paste CV text here..." className="w-full h-32 p-3 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none" />
              <button onClick={addPastedCv} disabled={!pasteName.trim() || !pasteText.trim()} className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition">Add Candidate</button>
            </div>
          )}

          {cvs.length > 0 && (
            <div className="mt-4 space-y-2">
              {cvs.map(cv => (
                <div key={cv.id} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                  <FileText className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <input type="text" value={cv.name} onChange={(e) => updateCvName(cv.id, e.target.value)} className="flex-1 bg-transparent text-sm font-medium text-slate-800 focus:outline-none focus:bg-white focus:px-2 focus:py-1 focus:rounded focus:border focus:border-slate-300" />
                  <span className="text-xs text-slate-500 hidden sm:inline">{cv.text.length} chars</span>
                  <button onClick={() => removeCv(cv.id)} className="p-1 text-slate-400 hover:text-red-600 transition"><X className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="mb-6">
          {error && (
            <div className="mb-3 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <span className="text-sm text-red-700">{error}</span>
            </div>
          )}
          <button onClick={runAnalysis} disabled={analyzing || !jdText.trim() || cvs.length === 0} className="w-full py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center justify-center gap-2">
            {analyzing ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> Analyzing {progress.current} of {progress.total}...</>
            ) : (
              <><Sparkles className="w-5 h-5" /> Run Shortlisting</>
            )}
          </button>
        </div>

        {results.length > 0 && (
          <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-slate-900">Ranked Shortlist</h2>
              {!analyzing && (
                <button onClick={downloadCsv} className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-sm font-medium text-slate-700 transition">
                  <Download className="w-4 h-4" />
                  Export CSV
                </button>
              )}
            </div>

            <div className="space-y-2">
              {results.map((r, i) => (
                <div key={r.id} className="border border-slate-200 rounded-lg overflow-hidden">
                  <button onClick={() => toggleExpand(r.id)} className="w-full flex items-center gap-4 p-4 hover:bg-slate-50 transition text-left">
                    <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-bold text-slate-700">#{i + 1}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-900 truncate">{r.name}</div>
                      {r.error && <div className="text-xs text-red-600 mt-0.5">Error: {r.error}</div>}
                    </div>
                    {!r.error && (
                      <>
                        <div className="hidden sm:block w-32">
                          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div className={`h-full ${scoreColor(r.score)} transition-all duration-500`} style={{ width: `${r.score}%` }} />
                          </div>
                        </div>
                        <div className={`text-2xl font-bold ${scoreText(r.score)} w-16 text-right`}>{r.score}%</div>
                      </>
                    )}
                    {expanded.has(r.id) ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
                  </button>

                  {expanded.has(r.id) && !r.error && (
                    <div className="px-4 pb-4 pt-2 border-t border-slate-100 bg-slate-50">
                      <div className="grid md:grid-cols-2 gap-4 mt-3">
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            <h4 className="text-sm font-semibold text-slate-800">Strengths</h4>
                          </div>
                          <ul className="space-y-1.5">
                            {r.strengths.map((s, idx) => (
                              <li key={idx} className="text-sm text-slate-700 pl-5 relative">
                                <span className="absolute left-0 text-emerald-600">✓</span>{s}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <XCircle className="w-4 h-4 text-red-500" />
                            <h4 className="text-sm font-semibold text-slate-800">Gaps</h4>
                          </div>
                          <ul className="space-y-1.5">
                            {r.gaps.map((g, idx) => (
                              <li key={idx} className="text-sm text-slate-700 pl-5 relative">
                                <span className="absolute left-0 text-red-500">•</span>{g}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="mt-6 text-center text-xs text-slate-400">
          Powered by Claude • Files are processed in your browser and never stored
        </div>
      </div>
    </div>
  );
}
