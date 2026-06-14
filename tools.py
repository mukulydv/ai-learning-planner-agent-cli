import os
from langchain.tools import tool
from langchain_pymupdf4llm import PyMuPDF4LLMLoader

def load_context_data(folder_name: str = "source_for_context") -> dict:
    """Reads context files (.pdf and .txt) from the folder and returns content & sources.
    
    Reads a maximum of 3 files.
    """
    # Try local directory first, fallback to script directory
    folder_path = folder_name
    if not os.path.exists(folder_path):
        folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder_name)
        
    if not os.path.exists(folder_path):
        return {"content": f"Error: Folder '{folder_name}' not found.", "sources": []}
        
    supported_extensions = ('.txt', '.pdf')
    files_to_read = []
    
    try:
        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith(supported_extensions):
                files_to_read.append(file_name)
    except Exception as e:
        return {"content": f"Error listing files in '{folder_path}': {str(e)}", "sources": []}
        
    # Limit to max 3 files
    files_to_read = files_to_read[:3]
    
    if not files_to_read:
        return {"content": f"No .txt or .pdf files found in the '{folder_name}' folder.", "sources": []}
        
    results = []
    sources = []
    for file_name in files_to_read:
        file_path = os.path.join(folder_path, file_name)
        file_ext = os.path.splitext(file_name)[1].lower()
        results.append(f"=== File: {file_name} ===")
        
        try:
            if file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                results.append(content)
                sources.append(file_name)
            elif file_ext == '.pdf':
                loader = PyMuPDF4LLMLoader(file_path)
                docs = loader.load()
                pdf_text = [doc.page_content for doc in docs if doc.page_content]
                results.append("\n".join(pdf_text))
                sources.append(file_name)
        except Exception as e:
            results.append(f"Error reading file: {str(e)}")
            
        results.append("\n" + "=" * 40 + "\n")
        
    return {
        "content": "\n".join(results),
        "sources": sources
    }

@tool
def get_context_for_time_table_planning() -> str:
    """Reads context files (.pdf and .txt) from the source_for_context folder.
    It reads a maximum of 3 files and returns their contents.
    """
    res = load_context_data()
    return res["content"]
