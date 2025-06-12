import arxiv
import json
import os
from typing import List
from mcp.server.fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
import time
import re

# Load environment variables
load_dotenv()

# Get Anthropic API key from environment
API_KEY = os.getenv("ANTHROPIC_API_KEY", "test_key")  # Default to test key for development

PAPER_DIR = "papers"
FDA_DIR = "fda_data"

# Initialize FastMCP server with SSE transport and capabilities
mcp = FastMCP(
    "research",
    transport="sse",
    host="0.0.0.0",
    port=3001,
    api_key=API_KEY,  # Using Anthropic API key
    capabilities={
        "tools": True,
        "resources": True,
        "prompts": True
    },
    zones={
        "firecrawl": {
            "name": "mcp_mcp-server-firecrawl",
            "config": {
                "unlocker": True,
                "timeout": 30000,
                "retries": 3
            }
        }
    }
)

@mcp.tool()
def root() -> dict:
    """
    Root endpoint that returns a welcome message.
    
    Returns:
        A dictionary containing the welcome message
    """
    return {"message": "Welcome to the Research Server API!"}

@mcp.tool()
def search_papers(topic: str, max_results: int = 5) -> List[str]:
    """
    Search for papers on arXiv based on a topic and store their information.
    
    Args:
        topic: The topic to search for
        max_results: Maximum number of results to retrieve (default: 5)
        
    Returns:
        List of paper IDs found in the search
    """
    
    # Use arxiv to find the papers 
    client = arxiv.Client()

    # Search for the most relevant articles matching the queried topic
    search = arxiv.Search(
        query = topic,
        max_results = max_results,
        sort_by = arxiv.SortCriterion.Relevance
    )

    papers = client.results(search)
    
    # Create directory for this topic
    path = os.path.join(PAPER_DIR, topic.lower().replace(" ", "_"))
    os.makedirs(path, exist_ok=True)
    
    file_path = os.path.join(path, "papers_info.json")

    # Try to load existing papers info
    try:
        with open(file_path, "r") as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Process each paper and add to papers_info  
    paper_ids = []
    for paper in papers:
        paper_ids.append(paper.get_short_id())
        paper_info = {
            'title': paper.title,
            'authors': [author.name for author in paper.authors],
            'summary': paper.summary,
            'pdf_url': paper.pdf_url,
            'published': str(paper.published.date())
        }
        papers_info[paper.get_short_id()] = paper_info
    
    # Save updated papers_info to json file
    with open(file_path, "w") as json_file:
        json.dump(papers_info, json_file, indent=2)
    
    print(f"Results are saved in: {file_path}")
    
    return paper_ids

@mcp.tool()
def extract_info(paper_id: str) -> str:
    """
    Search for information about a specific paper across all topic directories.
    
    Args:
        paper_id: The ID of the paper to look for
        
    Returns:
        JSON string with paper information if found, error message if not found
    """
 
    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as json_file:
                        papers_info = json.load(json_file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2)
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Error reading {file_path}: {str(e)}")
                    continue
    
    return f"There's no saved information related to paper {paper_id}."

@mcp.resource("papers://folders")
def get_available_folders() -> str:
    """
    List all available topic folders in the papers directory.
    
    This resource provides a simple list of all available topic folders.
    """
    folders = []
    
    # Get all topic directories
    if os.path.exists(PAPER_DIR):
        for topic_dir in os.listdir(PAPER_DIR):
            topic_path = os.path.join(PAPER_DIR, topic_dir)
            if os.path.isdir(topic_path):
                papers_file = os.path.join(topic_path, "papers_info.json")
                if os.path.exists(papers_file):
                    folders.append(topic_dir)
    
    # Create a simple markdown list
    content = "# Available Topics\n\n"
    if folders:
        for folder in folders:
            content += f"- {folder}\n"
        content += f"\nUse @{folder} to access papers in that topic.\n"
    else:
        content += "No topics found.\n"
    
    return content

@mcp.resource("papers://{topic}")
def get_topic_papers(topic: str) -> str:
    """
    Get detailed information about papers on a specific topic.
    
    Args:
        topic: The research topic to retrieve papers for
    """
    topic_dir = topic.lower().replace(" ", "_")
    papers_file = os.path.join(PAPER_DIR, topic_dir, "papers_info.json")
    
    if not os.path.exists(papers_file):
        return f"# No papers found for topic: {topic}\n\nTry searching for papers on this topic first."
    
    try:
        with open(papers_file, 'r') as f:
            papers_data = json.load(f)
        
        # Create markdown content with paper details
        content = f"# Papers on {topic.replace('_', ' ').title()}\n\n"
        content += f"Total papers: {len(papers_data)}\n\n"
        
        for paper_id, paper_info in papers_data.items():
            content += f"## {paper_info['title']}\n"
            content += f"- **Paper ID**: {paper_id}\n"
            content += f"- **Authors**: {', '.join(paper_info['authors'])}\n"
            content += f"- **Published**: {paper_info['published']}\n"
            content += f"- **PDF URL**: [{paper_info['pdf_url']}]({paper_info['pdf_url']})\n\n"
            content += f"### Summary\n{paper_info['summary'][:500]}...\n\n"
            content += "---\n\n"
        
        return content
    except json.JSONDecodeError:
        return f"# Error reading papers data for {topic}\n\nThe papers data file is corrupted."

@mcp.prompt()
def generate_search_prompt(topic: str, num_papers: int = 5) -> str:
    """Generate a prompt for Claude to find and discuss academic papers on a specific topic."""
    return f"""Search for {num_papers} academic papers about '{topic}' using the search_papers tool. 

    Follow these instructions:
    1. First, search for papers using search_papers(topic='{topic}', max_results={num_papers})
    2. For each paper found, extract and organize the following information:
       - Paper title
       - Authors
       - Publication date
       - Brief summary of the key findings
       - Main contributions or innovations
       - Methodologies used
       - Relevance to the topic '{topic}'
    
    3. Provide a comprehensive summary that includes:
       - Overview of the current state of research in '{topic}'
       - Common themes and trends across the papers
       - Key research gaps or areas for future investigation
       - Most impactful or influential papers in this area
    
    4. Organize your findings in a clear, structured format with headings and bullet points for easy readability.
    
    Please present both detailed information about each paper and a high-level synthesis of the research landscape in {topic}."""

@mcp.tool()
def search_fda(topic: str, max_results: int = 5) -> List[str]:
    """
    Search for FDA information and store results in topic-specific folders.
    
    Args:
        topic: The topic to search for (e.g., "recalls", "drugs", "food", "clinical")
        max_results: Maximum number of results to retrieve (default: 5)
        
    Returns:
        List of document IDs found in the search
    """
    
    print(f"\n=== Starting FDA Search for topic '{topic}' ===")
    print(f"FDA_DIR is set to: {FDA_DIR}")
    print(f"Current working directory: {os.getcwd()}")
    
    try:
        # Setup headers for requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        
        # Define search parameters based on topic
        if topic.lower() == 'recalls':
            search_url = 'https://api.fda.gov/food/enforcement.json'
            doc_type = 'recall'
            params = {
                'search': 'status:"Ongoing"',
                'limit': max_results,
                'sort': 'recall_initiation_date:desc'
            }
        elif topic.lower() == 'drugs':
            search_url = 'https://api.fda.gov/drug/event.json'
            doc_type = 'drug'
            params = {
                'limit': max_results,
                'sort': 'receivedate:desc'
            }
        elif topic.lower() == 'food':
            search_url = 'https://api.fda.gov/food/enforcement.json'
            doc_type = 'food'
            params = {
                'search': 'product_type:"food"',
                'limit': max_results,
                'sort': 'recall_initiation_date:desc'
            }
        elif topic.lower() == 'clinical':
            search_url = 'https://api.fda.gov/drug/event.json'  # Using drug events for clinical data
            doc_type = 'clinical'
            params = {
                'search': 'serious:1',  # Focus on serious clinical events
                'limit': max_results,
                'sort': 'receivedate:desc'
            }
        else:
            # For other topics, use the enforcement API with topic as search term
            search_url = 'https://api.fda.gov/food/enforcement.json'
            doc_type = 'general'
            params = {
                'search': f'reason_for_recall:"{topic}"',
                'limit': max_results,
                'sort': 'recall_initiation_date:desc'
            }
            
        print(f"\nSearching FDA {doc_type} API: {search_url}")
        print(f"Search parameters: {params}")
        
        # Create a session and get the data
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        results = data.get('results', [])
        
        print(f"Found {len(results)} results")
        
        # Process each result
        documents = []
        for idx, result in enumerate(results, 1):
            try:
                print(f"\nProcessing result {idx}/{len(results)}")
                
                # Generate a unique document ID
                doc_id = f"{doc_type}_{idx}_{datetime.now().strftime('%Y%m%d')}"
                print(f"Generated document ID: {doc_id}")
                
                # Extract information based on document type
                if doc_type in ['recall', 'food', 'general']:
                    doc_info = {
                        'id': doc_id,
                        'title': result.get('product_description', ''),
                        'summary': result.get('reason_for_recall', ''),
                        'date': result.get('recall_initiation_date', datetime.now().strftime('%Y-%m-%d')),
                        'type': doc_type,
                        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
                        'product_info': {
                            'product_name': result.get('product_description', ''),
                            'company_name': result.get('recalling_firm', ''),
                            'recall_number': result.get('recall_number', ''),
                            'recall_classification': result.get('classification', ''),
                            'recall_status': result.get('status', ''),
                            'distribution_pattern': result.get('distribution_pattern', ''),
                            'quantity': result.get('product_quantity', ''),
                            'state': result.get('state', ''),
                            'city': result.get('city', '')
                        }
                    }
                elif doc_type == 'drug':
                    doc_info = {
                        'id': doc_id,
                        'title': result.get('patient', {}).get('drug', [{}])[0].get('medicinalproduct', ''),
                        'summary': result.get('patient', {}).get('reaction', [{}])[0].get('reactionmeddrapt', ''),
                        'date': result.get('receiptdate', datetime.now().strftime('%Y-%m-%d')),
                        'type': doc_type,
                        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
                        'drug_info': {
                            'drug_name': result.get('patient', {}).get('drug', [{}])[0].get('medicinalproduct', ''),
                            'manufacturer': result.get('patient', {}).get('drug', [{}])[0].get('manufacturername', ''),
                            'dosage_form': result.get('patient', {}).get('drug', [{}])[0].get('drugdosageform', ''),
                            'route': result.get('patient', {}).get('drug', [{}])[0].get('drugadministrationroute', ''),
                            'indication': result.get('patient', {}).get('drug', [{}])[0].get('drugindication', '')
                        }
                    }
                elif doc_type == 'clinical':
                    doc_info = {
                        'id': doc_id,
                        'title': result.get('patient', {}).get('drug', [{}])[0].get('medicinalproduct', ''),
                        'summary': result.get('patient', {}).get('reaction', [{}])[0].get('reactionmeddrapt', ''),
                        'date': result.get('receiptdate', datetime.now().strftime('%Y-%m-%d')),
                        'type': doc_type,
                        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
                        'clinical_info': {
                            'study_phase': 'N/A',  # Drug events don't have phases
                            'conditions': [r.get('reactionmeddrapt', '') for r in result.get('patient', {}).get('reaction', []) if r.get('reactionmeddrapt')],
                            'interventions': [d.get('medicinalproduct', '') for d in result.get('patient', {}).get('drug', []) if d.get('medicinalproduct')],
                            'status': result.get('serious', 'Unknown'),
                            'sponsor': result.get('companynumb', 'Unknown'),
                            'locations': [result.get('occurcountry', 'Unknown')],
                            'enrollment': 1  # Drug events are per-patient
                        }
                    }
                
                print(f"Created document info for: {doc_info['title']}")
                documents.append(doc_info)
                print(f"Added document: {doc_id}")
                
            except Exception as e:
                print(f"Error processing result {idx}: {e}")
                continue

        # Create directory for this document type
        path = os.path.join(FDA_DIR, doc_type)  # Use doc_type instead of topic
        os.makedirs(path, exist_ok=True)
        
        file_path = os.path.join(path, "fda_info.json")
        print(f"\nSaving data to: {file_path}")
        
        # Try to load existing FDA info
        try:
            with open(file_path, "r") as json_file:
                fda_info = json.load(json_file)
        except (FileNotFoundError, json.JSONDecodeError):
            fda_info = {}

        # Add new documents to existing data
        doc_ids = []
        for doc in documents:
            doc_id = doc['id']
            fda_info[doc_id] = doc
            doc_ids.append(doc_id)

        # Save to JSON file using atomic write
        temp_file = file_path + '.tmp'
        try:
            with open(temp_file, "w") as json_file:
                json.dump(fda_info, json_file, indent=2)
            os.replace(temp_file, file_path)
            print(f"Results are saved in: {file_path}")
            return doc_ids
        except Exception as e:
            print(f"Error saving FDA data: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return []

    except Exception as e:
        print(f"Error in FDA search: {e}")
        return []

def extract_drug_info_from_content(content: str) -> dict:
    """Helper function to extract drug information from scraped content."""
    info = {
        'drug_name': '',
        'manufacturer': '',
        'dosage_form': '',
        'route': '',
        'indication': ''
    }
    
    # Extract drug name - look for patterns like "Drug Name:" or prominent mentions
    drug_name_match = re.search(r"Drug Name:?\s*([^\.]+)", content) or \
                     re.search(r"([A-Z][A-Za-z0-9\s\-]+(?:tablets|capsules|injection|solution))", content)
    if drug_name_match:
        info['drug_name'] = drug_name_match.group(1).strip()
    
    # Extract manufacturer
    manufacturer_match = re.search(r"Manufacturer:?\s*([^\.]+)", content) or \
                        re.search(r"([A-Z][A-Za-z\s,\.]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company))", content)
    if manufacturer_match:
        info['manufacturer'] = manufacturer_match.group(1).strip()
    
    # Extract dosage form
    dosage_match = re.search(r"Dosage Form:?\s*([^\.]+)", content) or \
                   re.search(r"(tablets|capsules|injection|solution|suspension)", content, re.IGNORECASE)
    if dosage_match:
        info['dosage_form'] = dosage_match.group(1).strip()
    
    # Extract route of administration
    route_match = re.search(r"Route:?\s*([^\.]+)", content) or \
                 re.search(r"(oral|intravenous|topical|subcutaneous|intramuscular)", content, re.IGNORECASE)
    if route_match:
        info['route'] = route_match.group(1).strip()
    
    # Extract indication
    indication_match = re.search(r"Indication:?\s*([^\.]+)", content) or \
                      re.search(r"indicated for\s+([^\.]+)", content, re.IGNORECASE)
    if indication_match:
        info['indication'] = indication_match.group(1).strip()
    
    return info

def extract_product_info_from_content(content: str, title: str, summary: str) -> dict:
    """Helper function to extract product information from scraped content."""
    info = {
        'product_name': '',
        'company_name': '',
        'recall_number': '',
        'recall_classification': '',
        'recall_status': '',
        'distribution_pattern': '',
        'quantity': '',
        'state': '',
        'city': ''
    }
    
    # Extract product name from title or content
    product_match = re.search(r"Product:?\s*([^\.]+)", content) or \
                   re.search(r"recalls\s+([^\.]+)", title)
    if product_match:
        info['product_name'] = product_match.group(1).strip()
    
    # Extract company name
    company_match = re.search(r"([A-Z][A-Za-z\s,\.]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company))", content)
    if company_match:
        info['company_name'] = company_match.group(1).strip()
    
    # Extract recall number
    recall_num_match = re.search(r"Recall Number:?\s*([^\.]+)", content)
    if recall_num_match:
        info['recall_number'] = recall_num_match.group(1).strip()
    
    # Extract recall classification
    class_match = re.search(r"Class ([I|II|III]+) Recall", content)
    if class_match:
        info['recall_classification'] = class_match.group(1)
    
    # Extract recall status
    status_match = re.search(r"Status:?\s*([^\.]+)", content)
    if status_match:
        info['recall_status'] = status_match.group(1).strip()
    
    # Extract distribution pattern
    dist_match = re.search(r"Distribution:?\s*([^\.]+)", content) or \
                re.search(r"distributed (?:to|in)\s+([^\.]+)", content, re.IGNORECASE)
    if dist_match:
        info['distribution_pattern'] = dist_match.group(1).strip()
    
    # Extract quantity if available
    quantity_match = re.search(r"Quantity:?\s*([^\.]+)", content)
    if quantity_match:
        info['quantity'] = quantity_match.group(1).strip()
    
    # Extract location information if available
    location_match = re.search(r"(?:in|from)\s+([A-Za-z\s]+),\s*([A-Z]{2})", content)
    if location_match:
        info['city'] = location_match.group(1).strip()
        info['state'] = location_match.group(2)
    
    return info

@mcp.resource("fda://{topic}")
def get_fda_documents(topic: str) -> str:
    """
    Get detailed information about FDA documents from a specific topic folder.
    
    Args:
        topic: The topic folder to retrieve FDA documents from (e.g., "recalls", "drugs", "food", "clinical")
    """
    # Map topic to doc_type
    doc_type_map = {
        'recalls': 'recall',
        'drugs': 'drug',
        'food': 'food',
        'clinical': 'clinical'
    }
    doc_type = doc_type_map.get(topic.lower(), topic.lower())
    
    topic_dir = os.path.join(FDA_DIR, doc_type)
    json_file = os.path.join(topic_dir, "fda_info.json")
    
    if not os.path.exists(json_file):
        return f"# No FDA documents found for {topic}\n\nTry searching for FDA documents first using search_fda('{topic}')"
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            fda_data = json.load(f)
        
        # Create markdown content with document details
        content = f"# FDA {topic.title()} Information\n\n"
        content += f"Total entries: {len(fda_data)}\n\n"
        
        # Sort entries by date
        sorted_entries = sorted(
            fda_data.items(),
            key=lambda x: datetime.strptime(x[1]['date'], '%Y-%m-%d') if '-' in x[1]['date'] 
            else datetime.strptime(x[1]['date'], '%m/%d/%Y'),
            reverse=True
        )
        
        for key, doc in sorted_entries:
            # Create section header based on document type
            if doc['type'] == 'recall':
                product = doc.get('product_info', {}).get('product_name', 'Unknown Product')
                company = doc.get('product_info', {}).get('company_name', 'Unknown Company')
                content += f"## {product} by {company}\n"
                content += f"- **Recall Date**: {doc['date']}\n"
                content += f"- **Recall Class**: {doc.get('product_info', {}).get('recall_classification', 'Not specified')}\n"
                content += f"- **Distribution**: {doc.get('product_info', {}).get('distribution_pattern', 'Not specified')}\n"
            elif doc['type'] == 'drug':
                drug_info = doc.get('drug_info', {})
                content += f"## {drug_info.get('drug_name', doc['title'])}\n"
                content += f"- **Date**: {doc['date']}\n"
                content += f"- **Manufacturer**: {drug_info.get('manufacturer', 'Not specified')}\n"
                content += f"- **Dosage Form**: {drug_info.get('dosage_form', 'Not specified')}\n"
                content += f"- **Route**: {drug_info.get('route', 'Not specified')}\n"
            elif doc['type'] == 'clinical':
                clinical_info = doc.get('clinical_info', {})
                content += f"## {doc['title']}\n"
                content += f"- **Date**: {doc['date']}\n"
                content += f"- **Phase**: {clinical_info.get('study_phase', 'Not specified')}\n"
                content += f"- **Status**: {clinical_info.get('status', 'Not specified')}\n"
                content += f"- **Sponsor**: {clinical_info.get('sponsor', 'Not specified')}\n"
            else:
                content += f"## {doc['title']}\n"
                content += f"- **Date**: {doc['date']}\n"
            
            if doc.get('url'):
                content += f"- **URL**: [{doc['url']}]({doc['url']})\n\n"
            
            if doc['summary']:
                content += f"### Summary\n{doc['summary']}\n\n"
            
            # Add type-specific additional information
            if doc['type'] == 'clinical':
                clinical_info = doc.get('clinical_info', {})
                if clinical_info.get('conditions'):
                    content += "### Conditions\n"
                    for condition in clinical_info['conditions']:
                        content += f"- {condition}\n"
                    content += "\n"
                if clinical_info.get('interventions'):
                    content += "### Interventions\n"
                    for intervention in clinical_info['interventions']:
                        content += f"- {intervention}\n"
                    content += "\n"
            
            content += "---\n\n"
        
        return content
    except json.JSONDecodeError:
        return f"# Error reading FDA data\n\nThe FDA data file is corrupted."
    except Exception as e:
        return f"# Error accessing FDA data\n\nError: {str(e)}"

@mcp.prompt()
def generate_fda_search_prompt(topic: str, max_results: int = 5) -> str:
    """Generate a prompt for Claude to find and analyze FDA information on a specific topic."""
    return f"""Search for {max_results} FDA documents about '{topic}' using the search_fda tool.

    Follow these instructions:
    1. First, search for FDA information using search_fda(topic='{topic}', max_results={max_results})
    2. For each document found, extract and analyze the following:
       - Document title and type (recall, safety alert, guidance, etc.)
       - Publication or effective date
       - Key findings or announcements
       - Affected products, companies, or populations
       - Recommended actions or precautions
       - Current status (if applicable)
       - Relevance to the topic '{topic}'
    
    3. Provide a comprehensive analysis that includes:
       - Overview of FDA's current position or guidance on '{topic}'
       - Common patterns or trends in the findings
       - Key safety concerns or regulatory considerations
       - Important updates or changes in FDA's approach
       - Recommendations for stakeholders
    
    4. If the search involves recalls or safety alerts:
       - Highlight urgent or active recalls/alerts
       - Summarize the scope and severity of issues
       - List specific products or batches affected
       - Detail required consumer/healthcare provider actions
    
    5. Organize the information in a clear, structured format with:
       - Executive summary
       - Detailed findings by document
       - Timeline of developments
       - Key takeaways and recommendations
    
    Please present both the detailed document information and a high-level analysis of FDA's perspective and actions regarding {topic}."""

def organize_fda_data(data: dict, doc_type: str) -> dict:
    """
    Organize FDA data based on document type.
    
    Args:
        data: Raw FDA data
        doc_type: Type of FDA document (recalls, drugs, food, clinical)
    
    Returns:
        Organized data structure
    """
    organized = {
        'id': data.get('id'),
        'title': data.get('title'),
        'url': data.get('url'),
        'date': data.get('date'),
        'type': doc_type,
        'summary': data.get('summary'),
        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Add type-specific information
    if doc_type == 'recall':
        organized.update({
            'recall_info': {
                'product_name': data.get('product_name'),
                'company_name': data.get('company_name'),
                'recall_class': data.get('recall_class'),
                'distribution': data.get('distribution'),
                'recall_reason': data.get('summary'),
                'status': 'active'
            }
        })
    elif doc_type == 'drug':
        organized.update({
            'drug_info': {
                'active_ingredients': data.get('active_ingredients', []),
                'dosage_form': data.get('dosage_form'),
                'administration': data.get('administration'),
                'approval_status': data.get('approval_status')
            }
        })
    elif doc_type == 'food':
        organized.update({
            'food_info': {
                'category': data.get('category'),
                'ingredients': data.get('ingredients', []),
                'allergens': data.get('allergens', []),
                'packaging': data.get('packaging')
            }
        })
    elif doc_type == 'clinical':
        organized.update({
            'clinical_info': {
                'study_phase': data.get('study_phase'),
                'conditions': data.get('conditions', []),
                'interventions': data.get('interventions', []),
                'status': data.get('status')
            }
        })
    
    # Add detailed content if available
    if 'key_points' in data:
        organized['key_points'] = data['key_points']
    if 'tables' in data:
        organized['tables'] = data['tables']
        
    return organized

@mcp.tool()
def save_fda_data(topic: str, data: List[dict]) -> List[str]:
    """
    Save FDA data to topic-specific folders with proper organization.
    
    Args:
        topic: The topic to save data for (recalls, drugs, food, clinical)
        data: List of FDA documents to save
        
    Returns:
        List of saved document IDs
    """
    try:
        print(f"\nSaving FDA data for topic: {topic}")
        print(f"Number of documents to save: {len(data)}")
        
        # Create base FDA directory if it doesn't exist
        if not os.path.exists(FDA_DIR):
            print(f"Creating FDA base directory: {FDA_DIR}")
            os.makedirs(FDA_DIR, exist_ok=True)
        
        # Create directory for this topic
        path = os.path.join(FDA_DIR, topic.lower().replace(" ", "_"))
        print(f"Creating topic directory: {path}")
        os.makedirs(path, exist_ok=True)
        
        file_path = os.path.join(path, "fda_info.json")
        print(f"Target file path: {file_path}")
        
        # Try to load existing FDA info
        try:
            with open(file_path, "r", encoding='utf-8') as json_file:
                fda_info = json.load(json_file)
                print(f"Loaded existing data with {len(fda_info)} documents")
        except (FileNotFoundError, json.JSONDecodeError):
            print("No existing data found, starting fresh")
            fda_info = {}
            
        # Process and save each document
        doc_ids = []
        for idx, doc in enumerate(data, 1):
            try:
                print(f"\nProcessing document {idx}/{len(data)}")
                
                # Generate document ID if not present
                if 'id' not in doc:
                    doc['id'] = f"{topic}_{idx}_{datetime.now().strftime('%Y%m%d')}"
                
                # Organize data based on document type
                organized_data = organize_fda_data(doc, topic)
                
                # Store document
                doc_id = organized_data['id']
                fda_info[doc_id] = organized_data
                doc_ids.append(doc_id)
                
                print(f"Processed document: {doc_id}")
                
            except Exception as e:
                print(f"Error processing document {idx}: {e}")
                continue
        
        # Save to JSON file
        if doc_ids:
            print(f"\nAttempting to save {len(doc_ids)} documents")
            
            # Create temporary file
            temp_file = file_path + '.tmp'
            try:
                # Write to temp file first
                print("Writing to temporary file...")
                with open(temp_file, "w", encoding='utf-8') as json_file:
                    json.dump(fda_info, json_file, indent=2, ensure_ascii=False)
                
                # Verify temp file
                print("Verifying temporary file...")
                with open(temp_file, "r", encoding='utf-8') as json_file:
                    test_load = json.load(json_file)
                    if not test_load:
                        raise ValueError("Empty JSON file")
                
                # Atomic rename
                print("Performing atomic rename...")
                os.replace(temp_file, file_path)
                print(f"Successfully saved {len(doc_ids)} documents to: {file_path}")
                
            except Exception as e:
                print(f"Error saving FDA data: {e}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return []
            
        return doc_ids
        
    except Exception as e:
        print(f"Error in save_fda_data: {e}")
        return []

@mcp.resource("fda://folders")
def get_fda_folders() -> str:
    """
    List all available FDA topic folders.
    """
    folders = []
    
    # Get all topic directories
    if os.path.exists(FDA_DIR):
        for topic_dir in os.listdir(FDA_DIR):
            topic_path = os.path.join(FDA_DIR, topic_dir)
            if os.path.isdir(topic_path):
                fda_file = os.path.join(topic_path, "fda_info.json")
                if os.path.exists(fda_file):
                    folders.append(topic_dir)
    
    # Create markdown content
    content = "# Available FDA Topics\n\n"
    if folders:
        for folder in folders:
            content += f"- {folder}\n"
        content += f"\nUse @{folder} to access FDA information in that topic.\n"
    else:
        content += "No FDA topics found. Try searching for FDA information first.\n"
    
    return content

if __name__ == "__main__":
    # Run MCP server
    #mcp.run(transport = 'stdio')
    mcp.run(transport = 'sse')
