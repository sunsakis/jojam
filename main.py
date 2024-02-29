from typing import Final
from telegram import ForceReply, Update, PreCheckoutQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
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
user_id = None
biker_id = None
ride_requests = {}

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        'Hit the paperclip and send your location to be picked up by a biker.'
    )
    context.user_data['state'] = 'USER_LOCATION'
    
async def handle_location(update: Update, context: CallbackContext) -> None:
    print(context.user_data['state'])
    print(update.message.location)
    if context.user_data['state'] == 'USER_LOCATION':
        user_location = update.message.location
        context.user_data['USER_LOCATION'] = user_location
        await update.message.reply_text(
            'Thanks for sharing your pick-up location. Now, hit the paperclip again and choose where you want to go to.'
        )
        context.user_data['state'] = 'DESTINATION'

    elif context.user_data['state'] == 'DESTINATION':
        user_destination = update.message.location
        context.user_data['DESTINATION'] = user_destination
        await update.message.reply_text('Bikers have been notified of your request to ride. When a biker accepts your request, they will let you know the price and estimated time of arrival.')
        global user_id
        user_id = update.message.from_user.id
         # Get driving route from Google Maps Directions API
        route = requests.get(
                'https://maps.googleapis.com/maps/api/directions/json',
                params={
                    'origin': f"{context.user_data['USER_LOCATION'].latitude},{context.user_data['USER_LOCATION'].longitude}",
                    'destination': f"{context.user_data['DESTINATION'].latitude}, {context.user_data['DESTINATION'].longitude}",
                    'key': GOOGLE_MAPS_API_KEY,
                },
                )
        
        location_address = gmaps.reverse_geocode((context.user_data['USER_LOCATION'].latitude, context.user_data['USER_LOCATION'].longitude))
        destination_address = gmaps.reverse_geocode((context.user_data['DESTINATION'].latitude, context.user_data['DESTINATION'].longitude))
        # Clean geocode to only include formatted address
        location_address = ','.join(location_address[0]['formatted_address'].split(',')[:3]).strip()
        destination_address = ','.join(destination_address[0]['formatted_address'].split(',')[:3]).strip()

        # Check if the route request was successful
        if route.status_code == 200:
            directions = route.json()

            # Check if a route was found
            if directions['routes']:
                # Get the first (best) route
                route = directions['routes'][0]

                # Get the overview polyline
                polyline = route['overview_polyline']['points']

                # Generate a static map URL with the route
                static_map_url = f"https://maps.googleapis.com/maps/api/staticmap?size=600x600&path=enc:{polyline}&key={GOOGLE_MAPS_API_KEY}"

            else:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Sorry, I couldn't find a route for your trip. Please try again later."
                )

        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="Sorry, I couldn't get the directions for your trip."
        )
            
        # Send user location, destination and price to the biker
        for chat_id in biker_ids:
            # Skip if user == biker
            if int(chat_id) != int(update.message.from_user.id): 
                # Send the route to every biker
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=static_map_url
                ) 
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text='NEW RIDE REQUEST! Pick-up: {}. Drop-off: {}.'.format(
                        location_address,
                        destination_address
                    ),
                    reply_markup=ForceReply(selective=True, input_field_placeholder='/invoice'),
                )
                # Store messageID and userID
                ride_requests[msg.message_id] = user_id

    elif context.user_data['state'] == 'BIKER_LOCATION':
        biker_location = update.edited_message.location
        context.user_data['BIKER_LOCATION'] = biker_location
        await update.edited_message.reply_text(
            'Shared your live location. Now go get your rider!'
        )
        # Send the biker's live location to the rider
        await context.bot.sendLocation(
            chat_id=user_id,
            latitude=biker_location.latitude,
            longitude=biker_location.longitude,
            live_period=86400,
            horizontal_accuracy=0
        )
        message_id = update.message.message_id
        context.user_data['message_id'] = message_id

        await context.bot.send_message(
            chat_id=user_id,
            text='Your biker is on the way!'
        )
        context.user_data['state'] = 'ON_THE_WAY'

    
    elif context.user_data['state'] == 'ON_THE_WAY':
        # Update the biker's location
        print(f'new location: {update.edited_message.location}')
        biker_location = update.edited_message.location
        await context.bot.editMessageLiveLocation(
            latitude=context.user_data['BIKER_LOCATION'].latitude,
            longitude=context.user_data['BIKER_LOCATION'].longitude,
            chat_id=user_id,
            message_id=context.user_data['message_id']
        )


async def join(update: Update, context: CallbackContext) -> None:
    context.user_data['state'] = 'CITY'
    chat_id = update.effective_chat.id
    if str(chat_id) not in biker_ids:
        context.user_data['chat_id'] = chat_id
        context.user_data['state'] = 'CITY'
        
        save_chat_ids(biker_ids)
        await update.message.reply_text(f'Joined the biker gang {chat_id}. To start receiving orders, write the name of the city you currently ride in.')
    else:
        await update.message.reply_text(f'Already in the biker gang {chat_id}. Write the name of the city you currently ride in.')
        context.user_data['chat_id'] = chat_id
        save_chat_ids(biker_ids)

async def handle_city(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'AWAITING_PRICE':
        return
    if context.user_data.get('state') == 'CITY':
        city = update.message.text
        biker_id = context.user_data['chat_id']
        biker_ids[str(biker_id)] = city
        save_chat_ids(biker_ids)
        await update.message.reply_text('Your city has been saved. You will be notified when someone needs a ride in {}'.format(city))
        context.user_data['state'] = 'IDLE'

async def help():
    return 'Contact @sunsakis if you need any assistance.'

async def invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extract the price from the command message
    command_text = update.message.text.split()
    if len(command_text) < 3:
        #await update.message.reply_text('Please provide the price in cents when invoicing. For example: "/invoice 700" sends an invoice for 7.00 EUR')
        await update.message.reply_text('When writing an /invoice command, you need to write the amount to charge and how quickly after payment can you pick the customer up. For example: "/invoice 700 5" sends an invoice for 7.00 EUR and lets your customer know you will arrive within 5 minutes after they make the payment. /invoice <price in cents> <time in minutes>')
        return
    try:
        invoice_price = int(command_text[1])
        min = int(command_text[2])
    except ValueError:
        #await update.message.reply_text('Please provide a valid price')
        await update.message.reply_text('Please provide a valid price')
        return

    # Define the price (in the smallest units of the currency, i.e. cents for EUR)
    price = {"label": "Permission To Ride", "amount": invoice_price}
    
    price_in_eur = invoice_price / 100
    # SEND INVOICE
    if update.message.reply_to_message:
        # Get messageID of original message
        message_id = update.message.reply_to_message.message_id
        # Get bikerID Who sent the invoice
        global biker_id
        biker_id = update.message.from_user.id
        # Check if messageID is in ride_requests
        if message_id in ride_requests:
            # Get userID of the ride request initiator
            user_id = ride_requests[message_id]
            print(ride_requests)
            await context.bot.send_invoice(
                chat_id= user_id,  # ID of the user to send the invoice to
                title= "Permission To Ride",
                description= f'Pick-up within {min}min after payment.',
                payload= 'Ride',
                provider_token= STRIPE_TOKEN,
                start_parameter= 'start_parameter',
                currency= 'EUR',
                prices= [price],
                send_phone_number_to_provider=True,
            )
            #await update.message.reply_text(f'Invoice sent for {price_in_eur} euros')
            await update.message.reply_text(f'Invoice sent for {price_in_eur} euros. You will be notified as soon as they pay, after which you will have {min} minutes to pick them up.')
    else:
        #await update.message.reply_text("You need to reply to a customer's message to send them an invoice")
        await update.message.reply_text("You need to reply to a ride request to send an invoice")

async def precheckout_callback(update: Update, context: CallbackContext):
    query: PreCheckoutQuery = update.pre_checkout_query
    print(query.order_info)
    # Check the payload, is this from your bot?
    if query.invoice_payload != "Ride":
        await query.answer(ok=False, error_message="Something went wrong...")
        return
    try:
        # Clear the shopping cart
        context.user_data[update.effective_user.id] = []
        # After successfully receiving payment
        await context.bot.send_message(
             chat_id= query.from_user.id,
             text= "Thank you for your payment. A biker is now coming to pick you up."
             )
        # Notify the seller
        await context.bot.send_message(
            chat_id=biker_id, text=f"Good news! The payment went through. Go get your rider!"
        )
    except Exception as e:
        # Log the error
        print(f"An error occurred while processing the payment: {e}")
        # Answer the pre-checkout query with an error message
        await query.answer(ok=False, error_message="An error occurred while processing your payment. Please try again.")
        return

    # If no errors occurred, answer the pre-checkout query with ok=True
    await query.answer(ok=True)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
                print(f'Update {update} caused error {context.error}')

if __name__ == '__main__':
    print("Babushka is waking up...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('join', join))
    app.add_handler(CommandHandler('help', help))
    app.add_handler(CommandHandler('invoice', invoice))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT, handle_city))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))

    # Errors
    app.add_error_handler(error)

    #Waiting
    app.run_polling(poll_interval=1)