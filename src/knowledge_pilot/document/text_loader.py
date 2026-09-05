def load_text(file_path):
    with open(file_path, mode="r", encoding="utf-8") as file:
        text = file.read()

    return text


def chunk_text(text, chunk_size, overlap):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i : i + chunk_size])
        if i + chunk_size >= len(text):
            break
    return chunks


if __name__ == "__main__":
    test_text = load_text("D:/AI_develop/KnowledgePilot/data/v04_long_test.txt")

    print("总字符数：", len(test_text))

    chunk_size = 500
    overlap = 100
    chunks = chunk_text(test_text, chunk_size, overlap)

    print("Chunk数量：", len(chunks))
    print("第一个Chunk长度：", len(chunks[0]))
    print("最后一个Chunk长度：", len(chunks[-1]))
    print(
        "Overlap是否正确：",
        chunks[0][-100:] == chunks[1][:100]
    )
