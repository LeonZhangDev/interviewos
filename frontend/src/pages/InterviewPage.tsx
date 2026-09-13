import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, BrainCircuit, Clock3, Gauge, MessageSquareText, Mic, MicOff, Sparkles, Volume2 } from 'lucide-react'
import { api, streamInterviewTurn } from '../api'
import type { InterviewScriptItem, InterviewSession, InterviewerPersona, TimeStatus } from '../types'

const focuses = ['Python', 'FastAPI', 'Agent', 'RAG', 'Database', 'Project', 'LeetCode', 'System Design']
const durationPresets = [30, 45, 60]

type ChatItem = { role: 'interviewer' | 'candidate' | 'feedback'; text: string; score?: number }

export function InterviewPage() {
  const [selected, setSelected] = useState(['Python', 'FastAPI', 'Agent', 'Project'])
  const [duration, setDuration] = useState(45)
  const [personas, setPersonas] = useState<InterviewerPersona[]>([])
  const [personaId, setPersonaId] = useState('normal')
  const [session, setSession] = useState<InterviewSession | null>(null)
  const [mainIndex, setMainIndex] = useState(0)
  const [currentPrompt, setCurrentPrompt] = useState('')
  const [activeQuestionId, setActiveQuestionId] = useState<number | undefined>()
  const [answer, setAnswer] = useState('')
  const [chat, setChat] = useState<ChatItem[]>([])
  const [busy, setBusy] = useState(false)
  const [timeStatus, setTimeStatus] = useState<TimeStatus | null>(null)
  const [recording, setRecording] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const recognitionRef = useRef<any>(null)
  const transcriptRef = useRef('')
  const startedAtRef = useRef(0)
  const recordingSessionRef = useRef<number | null>(null)

  const currentMain = useMemo(() => session?.script[mainIndex], [session, mainIndex])
  const speechAvailable = typeof window !== 'undefined' && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  useEffect(() => {
    api.interviewPersonas().then(setPersonas).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!session) return undefined
    const timer = window.setInterval(() => {
      api.interviewTimeStatus(session.id).then(setTimeStatus).catch(() => undefined)
    }, 30000)
    return () => window.clearInterval(timer)
  }, [session])

  function toggle(x: string) { setSelected((current) => current.includes(x) ? current.filter((i) => i !== x) : [...current, x]) }

  async function refreshTimeStatus(sessionId: number, moduleIndex?: number) {
    try {
      const status = moduleIndex === undefined
        ? await api.interviewTimeStatus(sessionId)
        : await api.startInterviewModule(sessionId, moduleIndex)
      setTimeStatus(status)
    } catch { /* keep last known status */ }
  }

  async function activate(item: InterviewScriptItem, index: number, sessionId?: number, resetChat = false) {
    setMainIndex(index); setCurrentPrompt(item.prompt); setActiveQuestionId(item.question_id); setAnswer('')
    transcriptRef.current = ''
    if (resetChat) setChat([{ role: 'interviewer', text: item.prompt }])
    else setChat((items) => [...items, { role: 'interviewer', text: item.prompt }])
    const target = sessionId ?? session?.id
    if (target) await refreshTimeStatus(target, index)
  }

  async function generate() {
    const created = await api.createInterview({ role: 'AI / Agent Engineer', focus: selected, difficulty: 'medium', duration, persona: personaId })
    setSession(created)
    await activate(created.script[0], 0, created.id, true)
  }

  function speakQuestion() {
    if (!currentPrompt || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(currentPrompt)
    utterance.lang = 'zh-CN'
    utterance.rate = 0.95
    window.speechSynthesis.speak(utterance)
  }

  async function startVoiceAnswer() {
    if (!session || recording) return
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = media
      chunksRef.current = []
      transcriptRef.current = ''
      setAnswer('')
      recordingSessionRef.current = session.id
      startedAtRef.current = Date.now()
      const recorder = new MediaRecorder(media)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        const elapsed = Date.now() - startedAtRef.current
        try {
          const sid = recordingSessionRef.current
          if (sid && blob.size) {
            setVoiceStatus('正在保存录音…')
            const saved = await api.uploadRecording(sid, blob)
            await api.saveRecordingTranscript(sid, saved.id, transcriptRef.current, elapsed)
            setVoiceStatus(`录音已保存 · ${Math.max(1, Math.round(elapsed / 1000))}s${speechAvailable ? ' · 转写已同步' : ''}`)
          }
        } catch (error) { setVoiceStatus(`录音保存失败：${String(error)}`) }
        streamRef.current?.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
      recorder.start(250)

      const SpeechRecognitionCtor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SpeechRecognitionCtor) {
        const recognition = new SpeechRecognitionCtor()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.lang = 'zh-CN'
        recognition.onresult = (event: any) => {
          let text = ''
          for (let i = 0; i < event.results.length; i += 1) text += event.results[i][0]?.transcript || ''
          transcriptRef.current = text.trim()
          setAnswer(text.trim())
        }
        recognition.onerror = () => setVoiceStatus('语音转写不可用，但录音仍会保存。你可以手动填写回答。')
        recognitionRef.current = recognition
        recognition.start()
      }
      setRecording(true)
      setVoiceStatus(speechAvailable ? '正在录音并实时转写…' : '正在录音；当前浏览器不支持 Speech Recognition，请手动填写回答。')
    } catch (error) {
      setVoiceStatus(`无法访问麦克风：${String(error)}`)
    }
  }

  function stopVoiceAnswer() {
    recognitionRef.current?.stop?.()
    recognitionRef.current = null
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop()
    setRecording(false)
  }

  async function submitAnswer() {
    if (!session || !currentPrompt || !answer.trim()) return
    if (recording) stopVoiceAnswer()
    const userText = answer.trim(); setAnswer(''); setBusy(true)
    transcriptRef.current = ''
    setChat((items) => [...items, { role: 'candidate', text: userText }])
    try {
      let streamed = ''
      let feedbackAdded = false
      setChat((items) => [...items, { role: 'interviewer', text: '' }])
      await streamInterviewTurn(session.id, { question_id: activeQuestionId, module_index: mainIndex, interviewer_prompt: currentPrompt, answer: userText }, (event, data) => {
        if (event === 'analysis' && !feedbackAdded) {
          feedbackAdded = true
          setChat((items) => {
            const copy = [...items]
            copy.splice(Math.max(0, copy.length - 1), 0, { role: 'feedback', text: `${data.feedback}\n薄弱点：${data.weakness}`, score: data.score })
            return copy
          })
        }
        if (event === 'token') {
          streamed += data.content || ''
          setChat((items) => {
            const copy = [...items]
            const last = copy[copy.length - 1]
            if (last?.role === 'interviewer') copy[copy.length - 1] = { ...last, text: streamed }
            return copy
          })
        }
        if (event === 'done') setCurrentPrompt(data.followup || streamed)
      })
      await refreshTimeStatus(session.id)
    } catch (error) {
      setChat((items) => [...items, { role: 'feedback', text: String(error), score: 0 }])
    } finally { setBusy(false) }
  }

  function nextMainQuestion() {
    if (!session) return
    if (recording) stopVoiceAnswer()
    const next = Math.min(session.script.length - 1, mainIndex + 1)
    if (next === mainIndex) return
    activate(session.script[next], next)
  }

  return (
    <div className="page-stack">
      <div className="page-header"><div><span className="eyebrow">AI 面试 · 语音</span><h1>选择你的面试官，然后真的开口回答。</h1><p>v0.9 支持 7 种面试官风格（只改提问与评分侧重，不改事实标准）、跨轮次面试官记忆与分模块时间控制；浏览器支持时可边说边转文字。</p></div></div>
      <section className="two-col interview-config">
        <div className="card panel">
          <h2>面试配置</h2><label className="field-label">目标岗位</label><div className="fake-input">AI / Agent Engineer</div>
          <label className="field-label">重点方向</label><div className="tag-selector">{focuses.map((x) => <button key={x} onClick={() => toggle(x)} className={selected.includes(x) ? 'tag selected' : 'tag'}>{x}</button>)}</div>
          <label className="field-label">时长</label>
          <div className="duration-presets">{durationPresets.map((preset) => <button key={preset} className={duration === preset ? 'preset selected' : 'preset'} onClick={() => setDuration(preset)}>{preset} min</button>)}</div>
          <input type="range" min="15" max="90" step="5" value={duration} onChange={(e) => setDuration(Number(e.target.value))} /><div className="duration-display"><Clock3 size={16} /> {duration} min</div>
          <label className="field-label">面试官风格</label>
          <div className="persona-grid">
            {personas.length ? personas.map((persona) => (
              <button key={persona.id} className={personaId === persona.id ? 'persona-card selected' : 'persona-card'} onClick={() => setPersonaId(persona.id)}>
                <strong>{persona.label}</strong><small>{persona.description}</small>
              </button>
            )) : <p>面试官风格加载中…</p>}
          </div>
          <button className="primary wide" onClick={generate}><Sparkles size={16} /> 生成并开始面试</button>
          {session ? <div className="mini-script">{session.script.map((item, i) => <button key={`${item.type}-${i}`} className={i === mainIndex ? 'active' : ''} onClick={() => activate(item, i)}><span>{String(i + 1).padStart(2, '0')}</span><strong>{item.type}</strong><small>{item.minutes}m</small></button>)}</div> : null}
        </div>

        <div className="card panel live-interview">
          <div className="section-title"><div><span className="eyebrow">实时深挖</span><h2>{session ? `面试 #${session.id}` : '等待开始'}</h2></div><div className="button-row"><button className="icon-button" title="朗读当前问题" onClick={speakQuestion} disabled={!currentPrompt}><Volume2 size={17} /></button><BrainCircuit /></div></div>
          {session ? <>
            <div className="time-controller">
              <div className="time-overview"><Gauge size={15} /><span>已用 <b>{timeStatus ? timeStatus.elapsed_minutes.toFixed(1) : '0.0'}</b> / {session.duration} min</span>{timeStatus?.advisory ? <em>{timeStatus.advisory}</em> : null}</div>
              <div className="time-modules">
                {(timeStatus?.modules || session.script.map((item, i) => ({ index: i, type: item.type, planned_minutes: item.minutes, elapsed_minutes: 0, status: 'pending' as const, over_budget: false }))).map((module) => (
                  <div key={module.index} className={`time-chip ${module.status}${module.over_budget ? ' over' : ''}`}>
                    <b>{module.type}</b><span>{module.elapsed_minutes.toFixed(1)}m / {module.planned_minutes}m</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="chat-stream">{chat.map((item, i) => <div key={i} className={`chat-bubble ${item.role}`}><span>{item.role === 'candidate' ? '我' : item.role === 'feedback' ? `得分 ${item.score}` : '面试官'}</span><p>{item.text}</p></div>)}</div>
            <div className="interview-answer-box"><div className="answer-label-row"><label className="field-label">你的回答</label><button className={recording ? 'voice-button recording' : 'voice-button'} onClick={recording ? stopVoiceAnswer : startVoiceAnswer}>{recording ? <MicOff size={15} /> : <Mic size={15} />}{recording ? '停止录音' : '语音回答'}</button></div><textarea value={answer} onChange={(e) => { setAnswer(e.target.value); transcriptRef.current = e.target.value }} placeholder="先讲结论，再解释原因、边界和失败场景…" /><small className={recording ? 'voice-status recording' : 'voice-status'}>{voiceStatus || '录音会保存到个人工作台；浏览器支持时会实时转写。'}</small><div className="button-row"><button className="primary" disabled={busy || !answer.trim()} onClick={submitAnswer}><MessageSquareText size={15} /> {busy ? '评分中' : '提交回答并继续追问'}</button><button className="secondary" onClick={nextMainQuestion}>下一主问题 <ArrowRight size={14} /></button></div></div>
          </> : <div className="empty-state">选择方向与面试官风格后生成一套面试。</div>}
          {currentMain ? <div className="current-main-note">当前主问题：{currentMain.prompt}</div> : null}
        </div>
      </section>
    </div>
  )
}
