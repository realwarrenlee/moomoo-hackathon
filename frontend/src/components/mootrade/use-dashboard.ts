"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { DashboardFetchError, fetchDashboard } from "@/lib/mootrade"

type UseDashboardResult<T> = {
  data: T | null
  error: string | null
  loading: boolean
  refreshing: boolean
  refreshedAt: Date | null
  refresh: () => void
}

export function useDashboard<T>(
  path: string,
  refreshMs = 60_000
): UseDashboardResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)
  const active = useRef(true)

  const load = useCallback(
    async (background: boolean) => {
      if (background) setRefreshing(true)
      else setLoading(true)
      try {
        const next = await fetchDashboard<T>(path)
        if (!active.current) return
        setData(next)
        setError(null)
        setRefreshedAt(new Date())
      } catch (caught) {
        if (!active.current) return
        setError(
          caught instanceof DashboardFetchError
            ? caught.message
            : "The dashboard API is unreachable. Start the local MooTrade API."
        )
      } finally {
        if (!active.current) return
        setLoading(false)
        setRefreshing(false)
      }
    },
    [path]
  )

  useEffect(() => {
    active.current = true
    void load(false)
    let timer: ReturnType<typeof setInterval> | undefined
    if (refreshMs > 0) {
      timer = setInterval(() => {
        if (document.visibilityState === "visible") void load(true)
      }, refreshMs)
    }
    return () => {
      active.current = false
      if (timer) clearInterval(timer)
    }
  }, [load, refreshMs])

  return {
    data,
    error,
    loading,
    refreshing,
    refreshedAt,
    refresh: () => void load(true),
  }
}
