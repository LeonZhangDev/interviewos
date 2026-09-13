import { afterEach, describe, expect, it, vi } from 'vitest'
import { setAuthTokens, streamInterviewTurn } from '../api'

function sseResponse(frames: string[]): Response {
  let index = 0
  const encoder = new TextEncoder()
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          index < frames.length
            ? { done: false, value: encoder.encode(frames[index++]) }
            : { done: true, value: undefined },
      }),
    },
  } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('streamInterviewTurn SSE parsing', () => {
  it('parses event/data frames split across chunk boundaries and ignores malformed frames', async () => {
    setAuthTokens('access-1', 'refresh-1')
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: question\nda',
        'ta: {"q": 1}\n\nev',
        'ent: feedback\ndata: {"f": 2}\n\n',
        'event: broken\ndata: not-json\n\n',
        'event: nodata\n\n',
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)

    const events: Array<[string, unknown]> = []
    await streamInterviewTurn(7, { interviewer_prompt: 'p', answer: 'a' }, (event, data) => {
      events.push([event, data])
    })

    expect(events).toEqual([
      ['question', { q: 1 }],
      ['feedback', { f: 2 }],
    ])

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/interviews/7/stream-turn')
    expect(init.method).toBe('POST')
    expect(init.headers.get('Authorization')).toBe('Bearer access-1')
    expect(JSON.parse(init.body)).toEqual({ interviewer_prompt: 'p', answer: 'a' })
  })

  it('falls back to the "message" event name when only a data line is present', async () => {
    setAuthTokens('access-1', '')
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(['data: {"x": 9}\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    const events: Array<[string, unknown]> = []
    await streamInterviewTurn(1, { interviewer_prompt: 'p', answer: 'a' }, (event, data) => {
      events.push([event, data])
    })

    expect(events).toEqual([['message', { x: 9 }]])
  })

  it('refreshes the token once and replays the stream after a 401', async () => {
    setAuthTokens('expired', 'refresh-1')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => 'expired' } as Response)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'new-access', refresh_token: 'new-refresh' }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(sseResponse(['event: done\ndata: {"ok": true}\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    const events: Array<[string, unknown]> = []
    await streamInterviewTurn(3, { interviewer_prompt: 'p', answer: 'a' }, (event, data) => {
      events.push([event, data])
    })

    expect(events).toEqual([['done', { ok: true }]])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/refresh')
    expect(fetchMock.mock.calls[2][1].headers.get('Authorization')).toBe('Bearer new-access')
  })
})
