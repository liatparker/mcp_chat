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
    Search for FDA information and store results in topic-specific folders using Bright Data.
    
    Args:
        topic: The topic to search for (e.g., "recalls", "drugs", "food", "clinical")
        max_results: Maximum number of results to retrieve (default: 5)
        
    Returns:
        List of document IDs found in the search
    """
    
    print(f"\n=== Starting FDA Search for topic '{topic}' using Bright Data ===")
    print(f"FDA_DIR is set to: {FDA_DIR}")
    
    try:
        # Define base FDA URLs and search parameters based on topic
        if topic.lower() == 'recalls':
            base_url = 'https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts'
            search_term = 'active recalls'
            doc_type = 'recall'
        elif topic.lower() == 'drugs':
            base_url = 'https://www.fda.gov/drugs/drug-safety-and-availability'
            search_term = 'drug safety'
            doc_type = 'drug'
        elif topic.lower() == 'food':
            base_url = 'https://www.fda.gov/food/recalls-outbreaks-emergencies'
            search_term = 'food safety recalls'
            doc_type = 'food'
        else:
            base_url = 'https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts'
            search_term = f'{topic} recalls'
            doc_type = 'general'

        # First use firecrawl_search to find relevant FDA pages
        search_results = mcp.call('mcp_mcp-server-firecrawl_firecrawl_search', {
            'query': f'site:fda.gov {search_term}',
            'limit': max_results,
            'scrapeOptions': {
                'formats': ['markdown'],
                'onlyMainContent': True
            }
        })

        documents = []
        for idx, result in enumerate(search_results.get('results', []), 1):
            try:
                # Use firecrawl_scrape to get detailed content from each page
                scrape_result = mcp.call('mcp_mcp-server-firecrawl_firecrawl_scrape', {
                    'url': result['url'],
                    'formats': ['markdown'],
                    'onlyMainContent': True
                })

                content = scrape_result.get('markdown', '')
                
                # Generate a unique document ID
                doc_id = f"{doc_type}_{idx}_{datetime.now().strftime('%Y%m%d')}"
                
                # Extract title and summary from content
                title = result.get('title', '').replace(' | FDA', '')
                summary = result.get('snippet', '')

                # Create document info based on type
                if doc_type in ['recall', 'food', 'general']:
                    doc_info = {
                        'id': doc_id,
                        'title': title,
                        'summary': summary,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'type': doc_type,
                        'url': result['url'],
                        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
                        'product_info': {
                            'product_name': title,
                            'company_name': '',  # Will be extracted from content
                            'recall_number': '',
                            'recall_classification': '',
                            'recall_status': 'Ongoing',
                            'distribution_pattern': '',
                            'quantity': '',
                            'state': '',
                            'city': ''
                        }
                    }
                    
                    # Extract product info from content
                    product_info = extract_product_info_from_content(content, title, summary)
                    doc_info['product_info'].update(product_info)
                    
                elif doc_type == 'drug':
                    doc_info = {
                        'id': doc_id,
                        'title': title,
                        'summary': summary,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'type': doc_type,
                        'url': result['url'],
                        'retrieved_date': datetime.now().strftime('%Y-%m-%d'),
                        'drug_info': {
                            'drug_name': title,
                            'manufacturer': '',
                            'dosage_form': '',
                            'route': '',
                            'indication': ''
                        }
                    }
                    
                    # Extract drug info from content
                    drug_info = extract_drug_info_from_content(content)
                    doc_info['drug_info'].update(drug_info)

                print(f"Created document info for: {doc_info['title']}")
                documents.append(doc_info)
                print(f"Added document: {doc_id}")

            except Exception as e:
                print(f"Error processing result {idx}: {e}")
                continue

        # Create directory for this topic
        path = os.path.join(FDA_DIR, topic.lower().replace(" ", "_"))
        os.makedirs(path, exist_ok=True)
        
        file_path = os.path.join(path, "fda_info.json")
        
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
        topic: The topic folder to retrieve FDA documents from (e.g., "recalls")
    """
    topic_dir = os.path.join(FDA_DIR, topic.lower().replace(" ", "_"))
    json_file = os.path.join(topic_dir, "fda_info.json")
    
    if not os.path.exists(json_file):
        return f"# No FDA documents found in topic folder: {topic}\n\nTry searching for FDA documents first."
    
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
            # Create section header based on topic
            if topic.lower() == 'recalls':
                product = doc.get('product_name', 'Unknown Product')
                company = doc.get('company_name', 'Unknown Company')
                content += f"## {product} by {company}\n"
                content += f"- **Recall Date**: {doc['date']}\n"
                content += f"- **Recall Class**: {doc.get('recall_class', 'Not specified')}\n"
                content += f"- **Distribution**: {doc.get('distribution', 'Not specified')}\n"
            else:
                content += f"## {doc['title']}\n"
                content += f"- **Date**: {doc['date']}\n"
            
            content += f"- **URL**: [{doc['url']}]({doc['url']})\n\n"
            
            if doc['summary']:
                content += f"### Summary\n{doc['summary']}\n\n"
            
            if doc.get('detailed_info', {}).get('key_points'):
                content += "### Key Points\n"
                for point in doc['detailed_info']['key_points']:
                    content += f"- {point}\n"
                content += "\n"
            
            if doc.get('detailed_info', {}).get('tables'):
                content += "### Additional Information\n"
                for table in doc['detailed_info']['tables']:
                    if table.get('headers') and table.get('data'):
                        content += "| " + " | ".join(table['headers']) + " |\n"
                        content += "|" + "|".join(["---"] * len(table['headers'])) + "|\n"
                        for row in table['data']:
                            content += "| " + " | ".join(row) + " |\n"
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
    mcp.run(transport = 'stdio')
