# from mcp.client import Client

# # Connect to the MCP server
# client = Client("research", port=8001)

# # Simple example: list available paper folders
# print("Accessing papers://folders resource...")
# folders = client.resource("papers://folders")
# print(folders)

# # Example: search for some papers
# print("\nSearching for papers about 'machine learning'...")
# papers = client.tool("search_papers", topic="machine learning", max_results=2)
# print(f"Found papers: {papers}") 