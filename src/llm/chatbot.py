from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:50390",  #local llm url
    api_key="not-needed"
)

def system_prompt_generate(user_id: int, session_id: str):
    system_prompt = "You are a helpful train booking assistant.Here is all the information you have about the user's current bookings: The user has the following bookings: A booking for the 'Mumbai Rajdhani' train. It departs from 'New Delhi' and goes to 'Mumbai Central' on 2025-12-25 17:00:00. The status is CONFIRMED. A booking for the 'Mumbai Rajdhani' train. It departs from 'New Delhi' and goes to 'Mumbai Central' on 2025-12-25 17:00:00. The status is CONFIRMED. A booking for the 'Mumbai Rajdhani' train. It departs from 'New Delhi' and goes to 'Mumbai Central' on 2025-12-25 17:00:00. The status is CONFIRMED. "
    return system_prompt

def stream_llm_response(user_message: str, user_id: int, session_id: str):
    """
    Streams response from local LLM token-by-token.
    Returns a generator that yields text chunks.
    """
    system_prompt = system_prompt_generate(user_id, session_id)

    stream = client.chat.completions.create(
        model="mistral",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        stream=True,
        temperature=0.3,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content  


if __name__ == "__main__":
    user_query = "Show me my booking."
    print("Assistant:", end=" ", flush=True)
    for token in stream_llm_response(user_query, 12304, "SHSYX2834"):
        print(token, end="", flush=True)
    print("\n--- done ---")
    
