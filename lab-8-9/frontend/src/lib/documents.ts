import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { DocumentFull, DocumentSummary } from '@/lib/types'
import { usePlayer } from '@/stores/player'

export interface DocumentPatch {
  title?: string
  authors?: string[]
  text?: string
}

/** Save changes to a document and bring every view of it up to date:
 *  the reader's cache, the library list and, if it is open, the player. */
export function useUpdateDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: DocumentPatch }) => api.updateDocument(id, patch),
    onSuccess: (doc: DocumentFull) => {
      qc.setQueryData(['document', doc.id], doc)
      qc.setQueryData<DocumentSummary[]>(['documents'], (list) =>
        list?.map((d) => (d.id === doc.id ? { ...d, title: doc.title, authors: doc.authors, word_count: doc.word_count, minutes: doc.minutes, progress: doc.progress, sections: doc.sections } : d)),
      )
      void qc.invalidateQueries({ queryKey: ['spoken', doc.id] })
      void qc.invalidateQueries({ queryKey: ['documents'] })
      usePlayer.getState().reloadDocument(doc)
    },
  })
}
