import { useEffect, useState } from 'react'
import { api } from '../api'

type CallbackStatus = 'working' | 'done' | 'error'

/**
 * Handles the provider redirect for GitHub/Gitee OAuth: reads code+state from
 * the URL, exchanges them through the backend (which stores the encrypted
 * token), then returns to the projects page where connection status reloads.
 */
export function OAuthCallbackPage({ onFinished }: { onFinished: () => void }) {
  const [status, setStatus] = useState<CallbackStatus>('working')
  const [message, setMessage] = useState('正在完成 Git 授权…')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code') || ''
    const state = params.get('state') || ''
    const providerError = params.get('error') || params.get('error_description') || ''

    if (providerError) {
      setStatus('error')
      setMessage(`授权被提供商拒绝（${providerError}）。可以回到项目页重新发起授权。`)
      return
    }
    if (!code || !state) {
      setStatus('error')
      setMessage('回调参数缺失（没有 code/state）。请从项目页重新发起授权。')
      return
    }

    let cancelled = false
    api.gitCallback({ code, state })
      .then((result) => {
        if (cancelled) return
        setStatus('done')
        setMessage(`已绑定 ${result.provider === 'github' ? 'GitHub' : 'Gitee'} 账号 @${result.login}。正在返回项目页…`)
        setTimeout(onFinished, 900)
      })
      .catch((error) => {
        if (cancelled) return
        setStatus('error')
        setMessage(`授权失败：${errorText(error)}`)
      })
    return () => { cancelled = true }
  }, [onFinished])

  return (
    <div className="oauth-callback-screen">
      <section className="card oauth-callback-card">
        <div className="brand-mark">IO</div>
        <h1>Git 账号授权</h1>
        <p>{message}</p>
        {status !== 'working'
          ? <button className="primary wide" onClick={onFinished}>返回项目页</button>
          : <button className="secondary wide" onClick={onFinished}>稍后手动返回</button>}
      </section>
    </div>
  )
}

function errorText(error: unknown): string {
  return String(error)
    .replace(/^Error:\s*/, '')
    .replace(/^.*?"detail":"([^"]+)".*$/s, '$1')
}
