from openai import OpenAI
import os
import re
import json
import base64

"""

Used to fill in during scrape to avoid dead ends. Not used for Domino's.

"""


openai_api_key = os.getenv('OPENAI_API_KEY')

openai_client = OpenAI(api_key=openai_api_key)

def use_gpt_fill_input(memory, website_info, outerHTML, testing_mode=True):
    if testing_mode:
        return 'testing mode'
    website_screenshot = base64.b64encode(website_info).decode('utf-8')
    messages = [
        {"role": "system",
         "content": "You are an AI assistant that generates example input strings for HTML elements. Use information from the memory I will give you when needed. You have a python function give_string() which takes a string, you must use to return your final answer. ",
         },
        {"role": "user",
         "content": [
             {
                 "type": "text",
                 "text": f"Given the memory: {memory}, website screenshot: "
             },
             {
                 "type": "image_url",
                 "image_url": {
                     "url": f"data:image/jpeg;base64,{website_screenshot}"
                 }
             },
             {
                 "type": "text",
                 "text": f", and outerHTML: {outerHTML}, briefly reason step by step then give me the text that can be used to fill the input box using the python function give_string(). Remember the text you give me will be inputted directly into an element represented by the outerHTML I gave you. YOU MUST pass the parameter into give_string() directly, do not use variables."
             }
         ]}
    ]

    # Call GPT-4o with the messages
    response = openai_client.chat.completions.create(
        model='gpt-4o',
        messages=messages,
        max_tokens=500,
        temperature=0
    )


    result = response.choices[0].message.content.strip()
    print("GPT RESULT: \n", result)
    pattern = r'give_string\(["\']([^"\']*)["\']\)'


    match = re.search(pattern, result)

    if match:
        parameter = match.group(1)
        return parameter
    else:
        return ""

