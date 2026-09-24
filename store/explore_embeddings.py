# A throwaway learning script -- NOT part of the pipeline, nothing reads or
# writes the database. It exists to build intuition for what an embedding
# vector is, by letting you *see* similarity scores between sentences.
#
# Run (with Ollama running and `ollama pull nomic-embed-text` done):
#     python store/explore_embeddings.py
#
# It prints three things:
#   1. A similarity matrix: every sentence compared with every other.
#   2. A mini "retrieval": a question ranked against the sentences.
#   3. The same ranking with the search_query/search_document prefixes
#      turned OFF, so you can see whether the prefix convention (ADR-0026)
#      changes anything on this tiny example.

import math

# Reuse the real client and constants from embed.py, so this script talks
# to Ollama exactly the way the pipeline will. (Importing embed.py doesn't
# touch the database -- that only happens inside embed_chunks().)
from embed import DOCUMENT_PREFIX, OllamaEmbeddingClient

# The prefix for the *query* side. embed.py only ever needs the document
# prefix (it only stores things); this script is the first place the query
# prefix appears, and the future retrieval ticket will need it too.
QUERY_PREFIX = "search_query: "

# A tiny made-up "corpus": a few regulatory-flavoured sentences, plus two
# deliberately unrelated ones as controls. Watch where those two land.
SENTENCES = [
    "Banks must hold a minimum amount of capital against their risk exposures.",
    "Credit institutions are required to maintain minimum own funds.",
    "Firms must report suspicious transactions to the regulator.",
    "Consumers have the right to cancel a loan agreement within 14 days.",
    "My cat likes to sleep on the warm windowsill.",
    "The recipe calls for two cups of flour and a pinch of salt.",
]

QUESTION = "How much capital does a bank need to keep?"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    # Cosine similarity = "how much do these two arrows point the same way?"
    # 1.0 means same direction, 0 means unrelated (at right angles), and
    # negative means roughly opposite. It ignores how *long* the arrows are
    # and looks only at direction, which is what "similar meaning" is
    # supposed to be about.
    #
    # The formula: dot product divided by the product of the lengths.
    #   zip(a, b)  pairs up the two lists element by element, like LINQ's
    #              a.Zip(b), giving (a0, b0), (a1, b1), ...
    #   sum(...)   adds up the products: that's the dot product.
    #   math.sqrt(sum(x * x ...)) is the length (magnitude) of one vector.
    dot = sum(x * y for x, y in zip(a, b))
    length_a = math.sqrt(sum(x * x for x in a))
    length_b = math.sqrt(sum(y * y for y in b))
    return dot / (length_a * length_b)


def short(text: str, width: int = 34) -> str:
    # Trims a sentence so the printed tables stay readable: keep the first
    # `width` characters, adding "..." only if something was cut off. The
    # slice text[:width] means "characters from the start up to width".
    return text if len(text) <= width else text[: width - 3] + "..."


def print_matrix(vectors: list[list[float]]) -> None:
    # Prints a grid: row i, column j = similarity of sentence i to sentence j.
    # The diagonal is always 1.00 (a sentence is identical to itself).
    # Columns are labelled #1..#n to keep the grid narrow; the legend
    # underneath says which number is which sentence.
    print("       " + "".join(f"  #{n + 1:<3}" for n in range(len(vectors))))
    for i, row_vector in enumerate(vectors):
        # A list comprehension building one formatted cell per column.
        cells = "".join(
            f"  {cosine_similarity(row_vector, column_vector):.2f}"
            for column_vector in vectors
        )
        print(f"  #{i + 1:<3} {cells}")
    print()
    for i, sentence in enumerate(SENTENCES):
        print(f"  #{i + 1} = {sentence}")


def print_ranking(question_vector: list[float], document_vectors: list[list[float]]) -> None:
    # Scores every sentence against the question, then prints best-first.
    # This is the whole of "retrieval" in miniature: embed the question,
    # measure closeness to each stored vector, sort. pgvector will do the
    # same thing inside Postgres, with an index to make it fast at scale.
    scored = [
        (cosine_similarity(question_vector, vector), sentence)
        for vector, sentence in zip(document_vectors, SENTENCES)
    ]
    # sort(reverse=True) sorts tuples by their first element (the score),
    # highest first.
    scored.sort(reverse=True)
    for score, sentence in scored:
        print(f"  {score:.3f}  {short(sentence, 70)}")


def main() -> None:
    client = OllamaEmbeddingClient()

    # --- 1. Similarity matrix (documents embedded WITH the document prefix) ---
    print("=" * 72)
    print("1. How similar is every sentence to every other sentence?")
    print("   (1.00 = identical direction; lower = less related)")
    print("=" * 72)
    document_vectors = [client.embed(DOCUMENT_PREFIX + s) for s in SENTENCES]
    print(f"   Each sentence became a vector of {len(document_vectors[0])} numbers.")
    print(f"   First 5 numbers of sentence #1: {[round(x, 3) for x in document_vectors[0][:5]]}")
    print("   (Individual numbers mean nothing on their own -- only comparisons do.)\n")
    print_matrix(document_vectors)

    # --- 2. Mini retrieval, prefixes ON ---
    print()
    print("=" * 72)
    print(f"2. Retrieval: {QUESTION!r}")
    print("   query prefix + document prefix, as the real pipeline will do")
    print("=" * 72)
    question_vector = client.embed(QUERY_PREFIX + QUESTION)
    print_ranking(question_vector, document_vectors)

    # --- 3. Same thing, prefixes OFF ---
    print()
    print("=" * 72)
    print("3. Same question, but with NO prefixes on either side")
    print("   (compare the order and the score gaps with section 2)")
    print("=" * 72)
    bare_document_vectors = [client.embed(s) for s in SENTENCES]
    bare_question_vector = client.embed(QUESTION)
    print_ranking(bare_question_vector, bare_document_vectors)

    print()
    print("Things to look for:")
    print(" - Do the two capital/own-funds sentences score high with each other")
    print("   despite sharing almost no words?")
    print(" - Do the cat and recipe sentences score low against everything?")
    print(" - Does the question rank the capital sentences first?")
    print(" - Does turning the prefixes off change the order or shrink the gaps?")
    print("   (On six sentences the effect can be small -- it matters most across")
    print("   thousands of Chunks.)")


if __name__ == "__main__":
    main()
