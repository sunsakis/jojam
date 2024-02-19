from typing import Final
from telegram import Update, PreCheckoutQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, PreCheckoutQueryHandler, CallbackQueryHandler
from dotenv import load_dotenv
import googlemaps
import os, logging
import requests
import json

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
load_dotenv()

def load_chat_ids():
    try:
        with open('chat_ids.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_chat_ids(chat_ids):
    with open('chat_ids.json', 'w') as f:
        json.dump(chat_ids, f)

gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
TOKEN = os.getenv('TOKEN')
STRIPE_TOKEN = os.getenv('STRIPE_TOKEN')
BOT_USERNAME: Final = '@YourBabushkaBot'
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

biker_ids = load_chat_ids()

async def start(update: Update, context: CallbackContext) -> None:
    location_keyboard = KeyboardButton(text="Share Location", request_location=True)
    custom_keyboard = [[location_keyboard]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard)
    await update.message.reply_text(
        'Please share your location to start.',
        reply_markup=reply_markup
    )
    context.user_data['state'] = 'LOCATION'
    
async def handle_location(update: Update, context: CallbackContext) -> None:
    if context.user_data['state'] == 'LOCATION':
        user_location = update.message.location
        context.user_data['LOCATION'] = user_location
        print(user_location)
        print(context.user_data)

        await update.message.reply_text(
            'Thanks for sharing your location. Now, hit the paperclip and choose the location you want to get to.'
        )
        context.user_data['state'] = 'DESTINATION'

    elif context.user_data['state'] == 'DESTINATION':
        user_destination = update.message.location
        context.user_data['DESTINATION'] = user_destination
        await update.message.reply_text('How much do you want to pay for the ride?')
        print(update.message.location)
        print(context.user_data)
        context.user_data['state'] = 'PRICE'

async def handle_price(update: Update, context: CallbackContext) -> None:
    price = update.message.text
    context.user_data['price'] = price
    await update.message.reply_text('Thanks! You want to pay {} for the ride.'.format(price))

    # Send user location, destination and price to the biker
    for chat_id in biker_ids:
        await context.bot.send_message(
            chat_id=chat_id,
            text='User location: {}, {}. Destination: {}, {}. Price: {}.'.format(
                context.user_data['location'].latitude,
                context.user_data['location'].longitude,
                context.user_data['destination'].latitude,
                context.user_data['destination'].longitude,
                context.user_data['price'],
            )
        )

    # Get driving route from Google Maps Directions API
    # response = requests.get(
    #     'https://maps.googleapis.com/maps/api/directions/json',
    #     params={
    #         'origin': f'{user_location.latitude},{user_location.longitude}',
    #         'destination': f'{destination.latitude},{destination.longitude}',
    #         'key': GOOGLE_MAPS_API_KEY,
    #     },
    # )
    # data = response.json()

    # # Send route to the biker
    # await context.bot.send_message(chat_id=BIKER_ID, text=json.dumps(data['routes'][0]['legs'][0]['steps']))
        
async def join(update: Update, context: CallbackContext) -> None:
    context.user_data['state'] = 'CITY'
    chat_id = update.effective_chat.id
    if str(chat_id) not in biker_ids:
        context.user_data['chat_id'] = chat_id
        save_chat_ids(biker_ids)
        await update.message.reply_text(f'Joined the biker gang {chat_id}. To start receiving orders, write the name of the city you currently ride in.')
    else:
        await update.message.reply_text(f'Already in the biker gang {chat_id}. Write the name of the city you currently ride in.')
        context.user_data['chat_id'] = chat_id
        save_chat_ids(biker_ids)

async def handle_city(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'CITY':
        city = update.message.text
        biker_id = context.user_data['chat_id']
        biker_ids[str(biker_id)] = city
        save_chat_ids(biker_ids)
        await update.message.reply_text('Your city has been saved.')
        context.user_data['state'] = 'IDLE'

async def help_command(update: Update):
    #return 'Contact @duketeo if you need assistance'
    return '@duketeo'

async def invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extract the price from the command message
    # The command should be in the format "/invoice <price>"
    command_text = update.message.text.split()
    if len(command_text) < 2:
        #await update.message.reply_text('Please provide the price in cents when invoicing. For example: "/invoice 700" sends an invoice for 7.00 EUR')
        await update.message.reply_text('Please provide the price in cents when invoicing. For example: "/invoice 700" sends an invoice for 7.00 EUR')
        return
    try:
        invoice_price = int(command_text[1])
    except ValueError:
        #await update.message.reply_text('Please provide a valid price')
        await update.message.reply_text('Please provide a valid price')
        return

    # Define the price (in the smallest units of the currency, i.e. cents for EUR)
    price = {"label": "Babushka's Special", "amount": invoice_price}
    
    price_in_eur = invoice_price / 100

    if update.message.reply_to_message:
        # SEND INVOICE
        await context.bot.send_invoice(
            chat_id= update.message.reply_to_message.forward_from.id,  # ID of the user to send the invoice to
            title= "Babushka's Special",
            description= 'Scrumptious food made especially for you.',
            payload= 'Pica',
            provider_token= STRIPE_TOKEN,
            start_parameter= 'start_parameter',
            currency= 'EUR',
            prices= [price],
            need_shipping_address=True,
            send_phone_number_to_provider=True,
        )
        #await update.message.reply_text(f'Invoice sent for {price_in_eur} euros')
        await update.message.reply_text(f'Invoice sent for {price_in_eur} euros')
    else:
        #await update.message.reply_text("You need to reply to a customer's message to send them an invoice")
        await update.message.reply_text("You need to reply to a customer's message to send them an invoice")

# async def precheckout_callback(update: Update, context: CallbackContext):
#     query: PreCheckoutQuery = update.pre_checkout_query
#     print(query.order_info.shipping_address.country_code, query.order_info.shipping_address.city)
#     # check the payload, is this from your bot?
#     if query.invoice_payload != "Pica":
#         #await query.answer(ok=False, error_message="Something went wrong...")
#         await query.answer(ok=False, error_message="Kažkas ne taip...")
#         return
#     elif query.order_info.shipping_address.country_code != 'LT' or query.order_info.shipping_address.city != 'Vilnius':
#         #await query.answer(ok=False, error_message="At the moment we can only deliver food in city: Vilnius, country: Lithuania")
#         await query.answer(ok=False, error_message="Šiuo metu pristatome tik Vilniuje")
#         return
        
#     try:
#         # Clear the shopping cart
#         context.user_data[update.effective_user.id] = []
#         # after successfully receiving payment
#         await context.bot.send_message(
#              chat_id= query.from_user.id,
#              #text= "Thank you for your payment. The courier will notify you when your food is ready"
#              text= "Liuks, apmokėta. Netrukus kurjeris pristatys maistuką."
#              )
#         # notify the seller
#         await context.bot.send_message(
#             #chat_id=BIKER_ID, text="Good news! The payment went through. What time should the courier be there to pick it up?"
#             chat_id=BIKER_ID, text=f"Naujas užsakymas! {query.from_user.first_name} {query.from_user.last_name} užsisakė"
#         )
#     except Exception as e:
#         # Log the error
#         print(f"An error occurred while processing the payment: {e}")
#         # Answer the pre-checkout query with an error message
#         #await query.answer(ok=False, error_message="An error occurred while processing your payment. Please try again.")
#         await query.answer(ok=False, error_message="An error occurred while processing your payment. Please try again.")
#         return

#     # If no errors occurred, answer the pre-checkout query with ok=True
#     await query.answer(ok=True)

# Responses
awaiting_response = False
    
# async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
#     global awaiting_response, user_id

#     # Send message from BIKER_ID if eater not BIKER_ID
#     if update.message.from_user.id == BIKER_ID and update.message.reply_to_message:
#         # Get eater ID from the reply message
#         user_id = update.message.reply_to_message.forward_from.id
#         print(f"User ID: {user_id} User name: {update.message.reply_to_message.forward_from.first_name}")
#         # Send chef's reply to eater
#         await context.bot.send_message(chat_id=user_id, text=update.message.text)
#     elif update.message.from_user.id == BIKER_ID and update.message.reply_to_message == None:
#         #return "You need to reply to the message to send a message." 
#         return "You need to reply to the message to send a message."    
#     else:
#         # Send eater's message to BIKER_ID
#         await context.bot.forward_message(chat_id=BIKER_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
#         #await context.bot.forward_message(chat_id=BIKER_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
#         return "Offer sent to bikers, they will get back to you soon. If you have anything else to say, just type here."
#     #return "Replied successfully. Once you find out their food fetishes, reply to the customer using /invoice command."
#     return "Perduota. Kai sutarsit dėl maisto, suvesk /saskaita komandą."
    
# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     text: str = update.message.text

#     print(text)

#     response: str = await handle_response(update, context)

#     if update.message is not None:
#         await update.message.reply_text(response)
#     else:
#         # Log the event for debugging purposes
#         logging.warning('Received an update with no message: %s', update)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
                print(f'Update {update} caused error {context.error}')

if __name__ == '__main__':
    print("Babushka is waking up...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('join', join))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT, handle_city))
    app.add_handler(MessageHandler(filters.TEXT, handle_price))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('saskaita', invoice_command))
    # app.add_handler(PreCheckoutQueryHandler(precheckout_callback))

    # Messages
    #app.add_handler(MessageHandler(filters.TEXT, handle_message))

    # Errors
    app.add_error_handler(error)

    #Waiting
    app.run_polling(poll_interval=1)