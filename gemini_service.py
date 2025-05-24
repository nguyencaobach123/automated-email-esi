import google.generativeai as genai
import config
from logger_config import logger
import time
import json

# Configure the Gemini API client
try:
    genai.configure(api_key=config.GEMINI_API_KEY)
    logger.info("Gemini API configured successfully.")
except Exception as e:
    logger.error(f"Failed to configure Gemini API: {e}", exc_info=True)
    raise  # Stop execution if API key is invalid/missing


# --- Model Initialization ---
# Initialize models globally or within functions as needed. Global can save overhead.
try:
    classification_model = genai.GenerativeModel(config.GEMINI_CLASSIFICATION_MODEL)
    generation_model = genai.GenerativeModel(config.GEMINI_GENERATION_MODEL)
    logger.info("Gemini models initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Gemini models: {e}", exc_info=True)
    classification_model = None
    generation_model = None


# --- Helper for Robust API Calls ---
def _call_gemini_api(model, prompt, max_retries=3, delay=5):
    """Calls the Gemini API with retry logic."""
    if model is None:
        logger.error(f"Model is not initialized. Cannot call API.")
        return None
    retries = 0
    while retries < max_retries:
        try:
            logger.debug(f"Calling Gemini model {model.model_name} (Attempt {retries + 1}/{max_retries})")
            # logger.debug(f"Prompt: {prompt[:500]}...") # Log truncated prompt
            response = model.generate_content(prompt)
            logger.debug(f"Gemini response received.")
            # Minimal check for safety/block reasons
            if not response.parts:
                 # Check if it was blocked
                 if response.prompt_feedback and response.prompt_feedback.block_reason:
                     logger.warning(f"Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
                     return None # Indicate blockage
                 else:
                     logger.warning(f"Gemini response has no parts. Potential issue.")
                     # return None

            return response # Return the full response object
        except Exception as e:
            retries += 1
            logger.warning(f"Gemini API call failed (Attempt {retries}/{max_retries}): {e}")
            if retries >= max_retries:
                logger.error(f"Gemini API call failed after {max_retries} attempts.")
                return None
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= 2 # Exponential backoff
    return None # Should not be reached if loop logic is correct

# --- Core Functions ---

def classify_email(email_subject: str, email_body: str) -> str | None:
    """
    Classifies email intent using Gemini.

    Args:
        email_subject: Subject of the email.
        email_body: Body content of the email.

    Returns:
        Classification category ('SPAM' or 'PROCESS') or None on failure/block.
    """
    prompt = f"""
    Phân tích nội dung email sau và phân loại mục đích chính của nó.
    Các danh mục phân loại là:
    - SPAM: Email rác không mong muốn, email lừa đảo, quảng cáo hoặc các câu hỏi hoàn toàn không liên quan đến cửa hàng kinh doanh
    - PROCESS: Email hợp lệ từ khách hàng như yêu cầu hỗ trợ, phản hồi, hoặc câu hỏi cần xử lý.

    Tiêu đề Email: {email_subject}
    Nội dung Email:
    ---
    {email_body[:2000]}
    ---

    Dựa *chỉ* vào văn bản đã cung cấp, trả về *chỉ* một phân loại: SPAM hoặc PROCESS. Không thêm giải thích gì.
    Phân loại:""" # Simple instruction

    logger.info("Attempting to classify email...")
    response = _call_gemini_api(classification_model, prompt)

    if response and response.parts:
        try:
            classification = response.text.strip().upper()
            if classification in ["SPAM", "PROCESS"]:
                logger.info(f"Email classified as: {classification}")
                return classification
            else:
                logger.warning(f"Received unexpected classification from Gemini: {classification}")
                return "PROCESS" # Safer default? Or return None to indicate ambiguity
        except Exception as e:
            logger.error(f"Error parsing classification response: {e}. Response text: {response.text}", exc_info=True)
            return None
    else:
        logger.error("Failed to get classification response from Gemini or request was blocked.")
        return None


def classify_query_intent(text: str) -> str | None:
    """
    Classifies the intent of the query text (FAQ or Product) using Gemini.

    Args:
        text: The query text content (e.g., email body).

    Returns:
        Classification category ('faq' or 'product') or None on failure/block.
    """
    if not text:
        logger.warning("Attempted to classify intent for empty text.")
        return None

    prompt = f"""
    Phân tích nội dung văn bản sau và phân loại mục đích chính của nó.
    Các danh mục phân loại là:
    - faq: Câu hỏi về các vấn đề chung, chính sách, dịch vụ, hướng dẫn sử dụng cơ bản, hoặc các câu hỏi không đề cập đến một sản phẩm cụ thể.
    - product: Câu hỏi hoặc yêu cầu thông tin liên quan đến một hoặc nhiều sản phẩm cụ thể (ví dụ: thông số kỹ thuật, giá, so sánh sản phẩm, tình trạng còn hàng, yêu cầu tư vấn mua sản phẩm).

    Nội dung văn bản:
    ---
    {text[:1500]}
    ---

    Dựa *chỉ* vào văn bản đã cung cấp, trả về *chỉ* một phân loại: faq hoặc product. Không thêm giải thích gì.
    Phân loại:"""

    logger.info("Attempting to classify query intent...")
    response = _call_gemini_api(classification_model, prompt) # Using classification_model

    if response and response.parts:
        try:
            classification = response.text.strip().lower()
            if classification in ["faq", "product"]:
                logger.info(f"Query intent classified as: {classification}")
                return classification
            else:
                logger.warning(f"Received unexpected query intent classification from Gemini: {classification}")
                return None # Return None to indicate ambiguity
        except Exception as e:
            logger.error(f"Error parsing query intent classification response: {e}. Response text: {response.text}", exc_info=True)
            return None
    else:
        logger.error("Failed to get query intent classification response from Gemini or request was blocked.")
        return None


def evaluate_knowledge_relevance(original_body: str, relevant_knowledge: list[dict]) -> bool:
    """
    Evaluates if the retrieved relevant knowledge is sufficient and relevant
    to answer the original email query using Gemini.

    Args:
        original_body: The body of the customer's email.
        relevant_knowledge: A list of dictionaries containing relevant info.

    Returns:
        True if the knowledge is deemed sufficient for a reply, False otherwise.
    """
    if not relevant_knowledge:
        logger.warning("evaluate_knowledge_relevance called with no relevant knowledge.")
        return False

    # Adapt context string creation for eBay items
    context_str = "Các sản phẩm liên quan được tìm thấy trên eBay:\n"
    for i, item in enumerate(relevant_knowledge): # relevant_knowledge now contains eBay items
        context_str += f"--- Sản phẩm {i+1} ---\n"
        context_str += f"Tiêu đề: {item.get('title', 'N/A')}\n"
        context_str += f"Giá: {item.get('price', 'N/A')}\n"
        context_str += f"Link: {item.get('itemWebUrl', 'N/A')}\n"
        context_str += f"Tình trạng: {item.get('condition', 'N/A')}\n"
        context_str += "---\n"


    prompt = f"""
    Dựa vào nội dung email gốc của khách hàng và thông tin về các sản phẩm liên quan được tìm thấy trên eBay, hãy đánh giá xem thông tin về các sản phẩm này có đủ và liên quan để trả lời đầy đủ câu hỏi hoặc vấn đề của khách hàng hay không.

    Nội dung Email gốc:
    ---
    {original_body[:1500]}
    ---

    Thông tin về các sản phẩm liên quan được tìm thấy trên eBay:
    ---
    {context_str[:4000]}
    ---

    Đánh giá: Thông tin về các sản phẩm eBay được tìm thấy có đủ và liên quan để trả lời email gốc không? Trả lời 'CÓ' hoặc 'KHÔNG', kèm theo giải thích ngắn gọn.
    Đánh giá:"""

    logger.info("Evaluating knowledge relevance using Gemini...")
    response = _call_gemini_api(generation_model, prompt) # Using generation_model for text evaluation

    if response and response.parts:
        try:
            evaluation = response.text.strip().upper()
            if evaluation.startswith("CÓ"):
                logger.info("Knowledge evaluated as relevant and sufficient.")
                return True
            else:
                logger.info(f"Knowledge evaluated as not relevant or insufficient. Evaluation: {evaluation}")
                return False
        except Exception as e:
            logger.error(f"Error parsing knowledge relevance evaluation response: {e}. Response text: {response.text}", exc_info=True)
            return False # Assume not sufficient on error
    else:
        logger.error("Failed to get knowledge relevance evaluation response from Gemini or request was blocked.")
        return False # Assume not sufficient on failure/block


def generate_response(original_subject: str, original_body: str, relevant_knowledge: list[dict]) -> str | None:
    """
    Generates a customer-friendly response using Gemini based on the original
    email and retrieved knowledge.

    Args:
        original_subject: The subject of the customer's email.
        original_body: The body of the customer's email.
        relevant_knowledge: A list of dictionaries containing relevant info.

    Returns:
        The generated email response text, or None on failure/block.
    """
    if not relevant_knowledge:
        logger.warning("generate_response called with no relevant knowledge.")

        return "Cảm ơn bạn đã liên hệ. Hiện tại chúng tôi chưa tìm thấy thông tin cụ thể về yêu cầu của bạn. Đội ngũ hỗ trợ của chúng tôi sẽ xem xét và phản hồi sau."

    # Construct context from eBay item results
    context_str = "Các sản phẩm liên quan được tìm thấy trên eBay:\n"
    for i, item in enumerate(relevant_knowledge): # relevant_knowledge now contains eBay items
        context_str += f"--- Sản phẩm {i+1} ---\n"
        context_str += f"Tiêu đề: {item.get('title', 'N/A')}\n"
        context_str += f"Giá: {item.get('price', 'N/A')}\n"
        context_str += f"Link: {item.get('itemWebUrl', 'N/A')}\n"
        context_str += f"Tình trạng: {item.get('condition', 'N/A')}\n"
        context_str += "---\n"
    
    prompt = f"""
    Bạn là trợ lý hỗ trợ khách hàng thân thiện và lịch sự.
    Một khách hàng đã gửi email sau:
    Tiêu đề: {original_subject}
    Nội dung:
    ---
    {original_body[:1500]}
    ---

    Dựa *chỉ* vào phần 'Các sản phẩm liên quan được tìm thấy trên eBay' bên dưới, hãy soạn một email trả lời hữu ích và ngắn gọn cho khách hàng.
    - Giải quyết câu hỏi hoặc vấn đề của khách hàng dựa trên email của họ.
    - Sử dụng thông tin về các sản phẩm eBay đã cung cấp để trả lời thắc mắc.
    - Đối với mỗi sản phẩm liên quan được liệt kê trong phần ngữ cảnh, hãy bao gồm Tiêu đề, Giá và Link sản phẩm.
    - Nếu thông tin sản phẩm có liên quan nhưng chưa đầy đủ, hãy ghi nhận điều này.
    - KHÔNG được tạo ra thông tin không có trong ngữ cảnh.
    - KHÔNG được trích dẫn trực tiếp từ các đoạn ngữ cảnh (ví dụ: không nói "Theo Sản phẩm 1..."). Hãy tổng hợp thông tin.
    - Nếu thông tin sản phẩm không liên quan, hãy lịch sự nói rằng bạn không tìm thấy sản phẩm phù hợp và đội ngũ sẽ xem xét yêu cầu.
    - Giữ giọng điệu chuyên nghiệp và thân thiện. Bắt đầu bằng lời chào lịch sự (ví dụ: "Kính gửi quý khách," hoặc "Xin chào,") và kết thúc phù hợp (ví dụ: "Trân trọng," hoặc "Thân mến,").
    - KHÔNG đưa email gốc của khách hàng vào phần trả lời.
    - Chỉ tạo *phần nội dung* của email trả lời.

    Các sản phẩm liên quan được tìm thấy trên eBay:
    ---
    {context_str[:4000]}
    ---

    Nội dung email trả lời:
    """

    logger.info("Generating response based on retrieved context...")
    response = _call_gemini_api(generation_model, prompt)

    if response and response.parts:
        try:
            generated_text = response.text.strip()
            logger.info("Response generated successfully.")
            logger.debug(f"Generated Response: {generated_text[:200]}...")
            return generated_text
        except Exception as e:
            logger.error(f"Error parsing generation response: {e}. Response text: {response.text}", exc_info=True)
            return None
    else:
        logger.error("Failed to get generation response from Gemini or request was blocked.")
        return None

def generate_ebay_search_params(email_body: str) -> dict | None:
    """
    Generates eBay Browse API search parameters based on email body using Gemini.

    Args:
        email_body: The body content of the email.

    Returns:
        A dictionary of eBay API parameters, or None on failure/block.
    """
    if not email_body:
        logger.warning("Attempted to generate eBay search parameters for empty email body.")
        return None

    prompt = f"""
    Bạn là một chuyên gia về API tìm kiếm của eBay Browse API (endpoint /item_summary/search).
    Dựa vào nội dung email của khách hàng, hãy xác định các tham số tìm kiếm phù hợp nhất để gọi API này.
    Mục tiêu là tìm kiếm các sản phẩm liên quan đến yêu cầu của khách hàng trên eBay.

    Đối với tham số 'q' trong kết quả JSON, hãy tuân thủ các quy tắc sau để kết hợp nhiều từ khóa:
    - Sử dụng dấu cách để phân tách các từ khóa khi bạn muốn tìm kiếm các mục bao gồm TẤT CẢ các từ khóa (AND request). Ví dụ: để tìm "iphone" VÀ "ipad", giá trị 'q' phải là `"iphone ipad"`.
    - Sử dụng dấu phẩy được bao quanh bởi dấu ngoặc đơn để phân tách các từ khóa khi bạn muốn tìm kiếm các mục bao gồm BẤT KỲ từ khóa nào trong danh sách (OR request). Ví dụ: để tìm "iphone" HOẶC "ipad", giá trị 'q' phải là `"(iphone, ipad)"`.

    Dưới đây là mô tả các tham số tìm kiếm có sẵn cho endpoint /item_summary/search:

    - q (string): Từ khóa tìm kiếm.
    - gtin (string): Tìm kiếm theo Global Trade Item Number (GTIN).
    - charity_ids (array of string): Lọc theo ID tổ chức từ thiện.
    - fieldgroups (array of string): Kiểm soát các nhóm trường trả về.
    - compatibility_filter (CompatibilityFilter): Lọc theo thuộc tính tương thích sản phẩm.
    - auto_correct (array of string): Bật tự động sửa lỗi từ khóa (giá trị: KEYWORD).
    - category_ids (array of string): Lọc theo ID danh mục.
    - filter (array of string): Mảng các bộ lọc trường để giới hạn/tùy chỉnh tập kết quả. Mỗi bộ lọc có định dạng 'tên_bộ_lọc:giá_trị'. Có thể sử dụng nhiều bộ lọc bằng cách thêm các chuỗi vào mảng.
    Ví dụ:
    - Lọc theo khoảng giá từ 10 đến 50 USD: "price:[10..50]", "priceCurrency:USD"
    - Lọc theo giá tối thiểu 10 USD: "price:[10]", "priceCurrency:USD"
    - Lọc theo giá tối đa 50 USD: "price:[..50]", "priceCurrency:USD"
    - Lọc theo tình trạng 'Mới' hoặc 'Đã sử dụng': "conditions:{{NEW|USED}}"
    - Lọc theo ID tình trạng (ví dụ: Mới - 1000, Đã sử dụng - 3000): "conditionIds:{{1000|3000}}"
    - Kết hợp nhiều bộ lọc (ví dụ: giá từ 10-50 USD và tình trạng Mới): ["price:[10..50]", "priceCurrency:USD", "conditions:{{NEW}}"]
    Tham khảo thêm tại https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html để biết danh sách đầy đủ các bộ lọc được hỗ trợ.
    - sort (array of SortField): Tiêu chí sắp xếp kết quả.
    - limit (string): Số lượng item trên mỗi trang.
    - offset (string): Số lượng item bỏ qua.
    - aspect_filter (AspectFilter): Lọc theo các khía cạnh của item.
    - epid (string): Lọc theo eBay product ID.

    Phân tích email sau và chỉ trả về một đối tượng JSON chứa các cặp key-value là tên tham số và giá trị tương ứng.
    Chỉ bao gồm các tham số thực sự cần thiết dựa trên yêu cầu của khách hàng trong email.
    Nếu không có yêu cầu cụ thể nào ngoài từ khóa sản phẩm, chỉ cần cung cấp tham số 'q'.
    Đảm bảo giá trị của các tham số tuân thủ đúng định dạng được mô tả.
    Ví dụ về định dạng JSON đầu ra:
    {{
      "q": "tên sản phẩm",
      "filter": ["price:[10..100]", "conditions:{{1000}}"],
      "sort": ["-price"],
      "limit": "50"
    }}
    Nếu không xác định được tham số nào ngoài từ khóa, chỉ trả về:
    {{
      "q": "từ khóa sản phẩm chính"
    }}
    Nếu không xác định được từ khóa sản phẩm, trả về JSON rỗng:
    {{}}

    Nội dung Email:
    ---
    {email_body[:2000]}
    ---

    Đối tượng JSON tham số tìm kiếm eBay:
    """

    logger.info("Attempting to generate eBay search parameters...")
    response = _call_gemini_api(generation_model, prompt) # Using generation_model

    if response and response.parts:
        try:
            json_string = response.text.strip()
            # Remove markdown code block fences if present
            if json_string.startswith("```json"):
                json_string = json_string[len("```json"):].strip()
            if json_string.endswith("```"):
                json_string = json_string[:-len("```")].strip()

            # Attempt to parse the JSON string
            params = json.loads(json_string)
            logger.info(f"Generated eBay search parameters: {params}")
            # Basic validation: ensure 'q' is present if other params are
            if params and "q" not in params and any(key in params for key in ["gtin", "charity_ids", "fieldgroups", "compatibility_filter", "auto_correct", "category_ids", "filter", "sort", "limit", "offset", "aspect_filter", "epid"]):
                 logger.warning("Generated parameters do not include 'q' despite other parameters being present. Returning None.")
                 return None
            return params
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing generated JSON parameters: {e}. Response text: {response.text}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing generated parameters: {e}", exc_info=True)
            return None
    else:
        logger.error("Failed to get eBay search parameters response from Gemini or request was blocked.")
        return None
