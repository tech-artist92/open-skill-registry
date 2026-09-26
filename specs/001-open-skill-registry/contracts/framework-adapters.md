# Copyright 2026 Open Skill Registry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Framework Adapters

The Open Skill Registry provides seamless integration with various popular AI agent frameworks through built-in adapters. This document outlines how to use these bridges to expose your skills as tools to different frameworks.

## 1. LangChain Bridge

You can instantly convert registered skills into LangChain compatible tools.

```python
from open_skill_registry import SkillRegistry
from langchain.agents import initialize_agent, AgentType
from langchain.llms import OpenAI

async def main():
    registry = SkillRegistry.from_config("osr.config.yaml")
    await registry.initialize()

    # Retrieve skills and convert to LangChain tools
    skills = await registry.search("data analysis")
    tools = registry.as_langchain_tools(skills)

    llm = OpenAI(temperature=0)
    agent = initialize_agent(
        tools, 
        llm, 
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
        verbose=True
    )
    
    agent.run("Analyze the latest sales data.")
```

## 2. OpenAI Bridge

Integrate directly with OpenAI's function calling API by converting skills to OpenAI tool formats.

```python
from open_skill_registry import SkillRegistry
import openai

async def main():
    registry = SkillRegistry.from_config("osr.config.yaml")
    await registry.initialize()

    skills = await registry.search("weather")
    tools = registry.as_openai_tools(skills)

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": "What's the weather in San Francisco?"}
        ],
        tools=tools,
        tool_choice="auto"
    )
    
    print(response.choices[0].message)
```

## 3. CrewAI Bridge

Use registered skills as custom tools in your CrewAI agents.

```python
from open_skill_registry import SkillRegistry
from crewai import Agent, Task, Crew

async def main():
    registry = SkillRegistry.from_config("osr.config.yaml")
    await registry.initialize()

    # Convert to tools suitable for CrewAI
    skills = await registry.search("web scraping")
    crew_tools = registry.as_langchain_tools(skills) # CrewAI uses LangChain tools natively

    researcher = Agent(
        role='Researcher',
        goal='Gather information from the web',
        backstory='An expert web researcher.',
        verbose=True,
        allow_delegation=False,
        tools=crew_tools
    )

    task = Task(
        description='Find the latest news about AI.',
        agent=researcher
    )

    crew = Crew(
        agents=[researcher],
        tasks=[task]
    )
    
    result = crew.kickoff()
    print(result)
```
