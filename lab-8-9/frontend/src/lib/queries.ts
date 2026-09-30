import { useQuery } from '@tanstack/react-query'

import { api } from './api'

export const useDocuments = () => useQuery({ queryKey: ['documents'], queryFn: api.documents })
export const useVoices = () => useQuery({ queryKey: ['voices'], queryFn: api.voices, staleTime: Infinity })
export const useHealth = () =>
  useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: (q) => (q.state.data?.status === 'ready' && q.state.data.asr_local !== 'loading' ? 30_000 : 1500),
    retry: false,
  })
export const useVoiceStatus = () => useQuery({ queryKey: ['voice-status'], queryFn: api.voiceStatus, refetchInterval: 10_000 })
export const useCommands = () => useQuery({ queryKey: ['commands'], queryFn: api.commands })
export const useLexicon = () => useQuery({ queryKey: ['lexicon'], queryFn: api.lexicon })
