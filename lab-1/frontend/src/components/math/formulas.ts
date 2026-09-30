/**
 * The assignment's formulas, transcribed from the PDF (pp. 2–3), plus the two the system
 * adds (the ‖D‖ = 1 reduction and Rocchio). Rendered with KaTeX by <Formula/>.
 */
export interface FormulaSpec {
  key: string;
  tex: string;
  number?: string;
  caption: string;
}

export const FORMULAS = {
  inverseFrequency: {
    key: "inverseFrequency",
    number: "1.5",
    tex: String.raw`B_i = \log\left(\frac{N}{P_i}\right)`,
    caption:
      "Inverse term frequency: N is the number of documents, P_i the number containing term i.",
  },
  rawWeight: {
    key: "rawWeight",
    number: "1.6",
    tex: String.raw`A_i^{\,j} = Q_i^{\,j} \times B_i`,
    caption:
      "Weight of term i in document j (used for keyword extraction): Q_i^j is its raw frequency in the document.",
  },
  matrixL: {
    key: "matrixL",
    number: "1.7",
    tex: String.raw`L = \{\forall i=\overline{1,N};\ j=\overline{1,D}:\ b_{ij} = \begin{cases}0, & t_j \notin l_i\\ 1, & t_j \in l_i\end{cases}\}`,
    caption: "The collection as an N × D matrix of document images over the dictionary of D terms.",
  },
  retrieval: {
    key: "retrieval",
    number: "1.8",
    tex: String.raw`L \times q = r`,
    caption: "Retrieval as a linear operation: the response vector r is the matrix applied to the query.",
  },
  normalizedWeight: {
    key: "normalizedWeight",
    tex: String.raw`w_{dk} = \frac{N_{dk}\,\log\dfrac{N}{N_k}}{\sqrt{\sum_j \left(N_{dj}\,\log\dfrac{N}{N_j}\right)^{2}}}`,
    caption:
      "Normalised TF-IDF weight of term k in document d: N_dk its count in d, N_k the documents containing it, N the collection size.",
  },
  documentVector: {
    key: "documentVector",
    tex: String.raw`D = \{w_{d1}, \dots, w_{dn}\}`,
    caption: "A document is the vector of its normalised term weights.",
  },
  queryVector: {
    key: "queryVector",
    tex: String.raw`Q = \{w_{q1}, \dots, w_{qn}\},\qquad w_{qj} = \begin{cases}1, & \text{word } j \in q\\ 0, & \text{otherwise}\end{cases}`,
    caption: "The query vector is binary: every query word weighs 1.",
  },
  cosine: {
    key: "cosine",
    tex: String.raw`r(D,Q) = \frac{(D,Q)}{\|D\| \cdot \|Q\|}`,
    caption: "Similarity is the cosine of the angle between the document and query vectors.",
  },
  normReduction: {
    key: "normReduction",
    tex: String.raw`\|D\| = 1 \;\Rightarrow\; r(D,Q) = \frac{\sum_{k \in q} w_{dk}}{\sqrt{|q|}}`,
    caption:
      "Because w_dk is already L2-normalised, ‖D‖ = 1 and the cosine reduces to a sum of stored weights over a constant.",
  },
  idfQuery: {
    key: "idfQuery",
    tex: String.raw`w_{qj} = B_j = \log\frac{N}{N_j}`,
    caption: "Improvement proposal 1: weight query words by their inverse frequency instead of 1.",
  },
  rocchio: {
    key: "rocchio",
    tex: String.raw`\vec{q}' = \alpha\,\vec{q} + \frac{\beta}{|D_r|}\sum_{d \in D_r}\vec{d} - \frac{\gamma}{|D_{nr}|}\sum_{d \in D_{nr}}\vec{d}`,
    caption:
      "Rocchio relevance feedback: move the query towards the documents marked relevant and away from those marked non-relevant.",
  },
} as const satisfies Record<string, FormulaSpec>;

export type FormulaKey = keyof typeof FORMULAS;
