from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from clients.web_search_tool import get_brave_tool
from clients.email_tool import send_email_tool
from clients.database_tool import db_tool
from clients.ingest_tool import ingest_file_tool, ingest_directory_tool
from clients.query_rag_tool import query_rag_tool
from clients.concept_map_tool import concept_map_tool
from clients.exam_tool import generate_exam_tool
from clients.lesson_plan_tool import lesson_plan_tool

def create_agent():
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

    tools = [
        get_brave_tool(),
        send_email_tool,
        db_tool,
        ingest_file_tool,
        ingest_directory_tool,
        query_rag_tool,
        concept_map_tool,
        generate_exam_tool, 
        lesson_plan_tool,
        
    ]

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="""Agisci come un assistente AI.
Se puoi rispondere direttamente, fallo.
Se serve uno strumento, usalo.
Usa solo strumenti disponibili tramite function calling."""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_functions_agent(llm=llm, tools=tools, prompt=prompt)

    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True
    )

    return agent_executor
