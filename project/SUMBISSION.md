#WEEK 2

#CONTENT(in project):
1) .gitignore
2) .env.example
3) agent.py
4) requirements.txt
5) submission.md




#agent.py:

    #features:
        1) A research tool able to search the web for relevant information and fetch it back to the model
        2) alphaxiv mcp server is used instead of manaul tool calling
        3) A custom user interface is made for the conversation
        4) the interface has a separate portion the show the tool activity as the conversation continues
        5) commands are added:  -ctrl+l: clear display
                                -ctrl+r: clear history
                                -ctrl+q: quit
                              

    #agent loop:
        first of all, the tools given by the mcp server were added to a list called openai_tools[]
        then the model is called and the message is stored as message
        if message has no tool_call, it returns the message
        else it enter a loop that for every toolcall, extracts the result, saves it and appends it to messages
        if it doesn't stop then iteration limit hits!! to prevent infinte tool calling loops.

    #design decision:
        made a separate panel for tool activity that shows the tool the model decides to call


    #difficulties and suprises:
        connecting the mcp server was such a headache, at point I thought manual tool calling was easier
        setting up the oauth authentication and understanding the mcp client workflow, this took lot of debugging
        understanding and implementing the tui was easier said than done


    # I should've given more time to understand and improve the user interface terminal, making it more aesthetic.


MODEL used = "openai/gpt-4o-mini"
ALPHAXIV_MCP_URL used = "https://api.alphaxiv.org/mcp/v1"
REDIRECT_URI used = "http://localhost:8765/callback"
TOKEN_FILE used = ".alphaxiv_tokens.json"