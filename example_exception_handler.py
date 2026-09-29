from ast import literal_eval
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.utils.translation import gettext as _
from payment.utils.translation import get_language_codes, translate_message
import logging
import json

logger = logging.getLogger(__name__)

# Constants for error keys
NON_FIELD_ERRORS_KEY = 'non_field_errors'
ALL_ERRORS_KEY = '__all__'


def get_error_summary(status_code, language_codes):
    summaries = {
        400: _("Please correct the errors in the form."),
        401: _("Authentication required, please login to continue."),
        403: _("You do not have permission to perform this action."),
        404: _("Resource not found."),
        405: _("Method not allowed."),
        429: _("Too many requests. Please try again later."),
        500: _("Internal server error. Please try again later."),
        503: _("Service unavailable. Please try again later."),
    }
    
    base_message = summaries.get(status_code, _("An error occurred."))
    
    multilingual = {}
    for lang_code in language_codes:
        multilingual[lang_code] = translate_message(base_message, lang_code)
    
    return json.dumps(multilingual, ensure_ascii=False)


def translate_errors_recursively(errors, language_codes):
    if isinstance(errors, dict):
        return {
            field: translate_errors_recursively(field_errors, language_codes)
            for field, field_errors in errors.items()
        }
    
    if isinstance(errors, list):
        # Check if this is a list of ErrorDetail objects
        if errors and hasattr(errors[0], 'code'):
            # Process ALL errors in the list (not just the first one)
            translated_list = []
            for error in errors:
                multilingual_error = {}
                for lang_code in language_codes:
                    multilingual_error[lang_code] = translate_message(
                        str(error), lang_code
                    )
                # Convert each error to a JSON string and add to array
                translated_list.append(json.dumps(multilingual_error, ensure_ascii=False))
            return translated_list
        
        # Handle nested structures
        return [
            translate_errors_recursively(error, language_codes)
            for error in errors
        ]
    
    # Single error message (edge case) - wrap in array for consistency
    multilingual_error = {}
    for lang_code in language_codes:
        multilingual_error[lang_code] = translate_message(
            str(errors), lang_code
        )
    return [json.dumps(multilingual_error, ensure_ascii=False)]


def _normalize_validation_errors(data):
    if isinstance(data, dict):
        return {
            key: _normalize_validation_errors(value)
            for key, value in data.items()
        }
    
    if isinstance(data, list):
        # Check if list contains stringified dict (model validation errors)
        if data and isinstance(data[0], str):
            try:
                # Use ast.literal_eval for safe parsing (no code execution)
                parsed = literal_eval(data[0])
                if isinstance(parsed, dict):
                    return parsed
            except (SyntaxError, ValueError, TypeError):
                # Not a dict string, return as-is
                pass
        
        # Normal list processing
        return [_normalize_validation_errors(item) for item in data]
    
    return data


def _extract_error_message(translated_errors, status_code, language_codes):
    if status_code == 400 and isinstance(translated_errors, dict):
        # Check for non-field errors (DRF serializer or Django model validation)
        error_list = (
            translated_errors.get(NON_FIELD_ERRORS_KEY) or 
            translated_errors.get(ALL_ERRORS_KEY)
        )
        
        if error_list and isinstance(error_list, list) and error_list:
            return error_list[0]
    
    return get_error_summary(status_code, language_codes)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        language_codes = get_language_codes()
        
        # Normalize model-level ValidationError strings into proper dict structure
        normalized_data = _normalize_validation_errors(response.data)
        
        # Translate all errors recursively
        translated_errors = translate_errors_recursively(normalized_data, language_codes)
        
        # Extract the most appropriate message for the response
        message = _extract_error_message(
            translated_errors, 
            response.status_code, 
            language_codes
        )
        
        response.data = {
            "status": "error",
            "code": response.status_code,
            "message": message,
            "errors": translated_errors,
        }
    else:
        # Handle unexpected/unhandled exceptions
        logger.error("Unhandled exception", exc_info=exc)
        language_codes = get_language_codes()
        return Response(
            {
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": get_error_summary(500, language_codes),
                "errors": {},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response