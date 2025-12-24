"""
Inspirational quotes for dashboard - rotated hourly per user.

This module provides a curated list of 100+ short, motivational quotes
from great minds. Each hour, users see a different set of quotes based
on their user ID and the current date + hour (deterministic rotation).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, List, Any
from django.utils import timezone


# Curated list of 120+ short quotes (no copyright-sensitive long passages)
QUOTES = [
    ("The best time to plant a tree was 20 years ago. The second best time is now.", "Chinese Proverb"),
    ("Success is not final, failure is not fatal: it is the courage to continue that counts.", "Winston Churchill"),
    ("Don't watch the clock; do what it does. Keep going.", "Sam Levenson"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Believe you can and you're halfway there.", "Theodore Roosevelt"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Everything you've ever wanted is on the other side of fear.", "George Addair"),
    ("Success is walking from failure to failure with no loss of enthusiasm.", "Winston Churchill"),
    ("Try not to become a person of success, but rather try to become a person of value.", "Albert Einstein"),
    ("It is not the strongest of the species that survive, nor the most intelligent, but the one most responsive to change.", "Charles Darwin"),
    ("Great things are done by a series of small things brought together.", "Vincent Van Gogh"),
    ("If you are not willing to risk the usual, you will have to settle for the ordinary.", "Jim Rohn"),
    ("Take up one idea. Make that one idea your life. Think of it, dream of it, live on that idea.", "Swami Vivekananda"),
    ("All progress takes place outside the comfort zone.", "Michael John Bobak"),
    ("People who are crazy enough to think they can change the world, are the ones who do.", "Rob Siltanen"),
    ("We may encounter many defeats but we must not be defeated.", "Maya Angelou"),
    ("Knowing is not enough; we must apply. Wishing is not enough; we must do.", "Johann Wolfgang Von Goethe"),
    ("Imagine your life is perfect in every respect; what would it look like?", "Brian Tracy"),
    ("We generate fears while we sit. We overcome them by action.", "Dr. Henry Link"),
    ("Whether you think you can or think you can't, you're right.", "Henry Ford"),
    ("Security is mostly a superstition. Life is either a daring adventure or nothing.", "Helen Keller"),
    ("The man who has confidence in himself gains the confidence of others.", "Hasidic Proverb"),
    ("The only limit to our realization of tomorrow will be our doubts of today.", "Franklin D. Roosevelt"),
    ("Creativity is intelligence having fun.", "Albert Einstein"),
    ("What you lack in talent can be made up with desire, hustle and giving 110% all the time.", "Don Zimmer"),
    ("Do what you can with all you have, wherever you are.", "Theodore Roosevelt"),
    ("Develop an 'Attitude of Gratitude'. Say thank you to everyone you meet for everything they do for you.", "Brian Tracy"),
    ("You are never too old to set another goal or to dream a new dream.", "C.S. Lewis"),
    ("To see what is right and not do it is a lack of courage.", "Confucius"),
    ("Reading is to the mind, as exercise is to the body.", "Brian Tracy"),
    ("Fake it until you make it! Act as if you had all the confidence you require until it becomes your reality.", "Brian Tracy"),
    ("The future belongs to the competent. Get good, get better, be the best!", "Brian Tracy"),
    ("For every reason it's not possible, there are hundreds of people who have faced the same circumstances and succeeded.", "Jack Canfield"),
    ("Things work out best for those who make the best of how things work out.", "John Wooden"),
    ("A room without books is like a body without a soul.", "Marcus Tullius Cicero"),
    ("I think goals should never be easy, they should force you to work, even if they are uncomfortable at the time.", "Michael Phelps"),
    ("One of the lessons that I grew up with was to always stay true to yourself and never let what somebody else says distract you from your goals.", "Michelle Obama"),
    ("Today's accomplishments were yesterday's impossibilities.", "Robert H. Schuller"),
    ("The only way to discover the limits of the possible is to go beyond them into the impossible.", "Arthur C. Clarke"),
    ("Don't count the days, make the days count.", "Muhammad Ali"),
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("A year from now you may wish you had started today.", "Karen Lamb"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
    ("What we think, we become.", "Buddha"),
    ("The mind is everything. What you think you become.", "Buddha"),
    ("Do not wait to strike till the iron is hot; but make it hot by striking.", "William Butler Yeats"),
    ("Act as if what you do makes a difference. It does.", "William James"),
    ("Success is the sum of small efforts, repeated day in and day out.", "Robert Collier"),
    ("If you want to lift yourself up, lift up someone else.", "Booker T. Washington"),
    ("I attribute my success to this: I never gave or took any excuse.", "Florence Nightingale"),
    ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
    ("The most difficult thing is the decision to act, the rest is merely tenacity.", "Amelia Earhart"),
    ("Every strike brings me closer to the next home run.", "Babe Ruth"),
    ("Definiteness of purpose is the starting point of all achievement.", "W. Clement Stone"),
    ("Life is 10% what happens to me and 90% of how I react to it.", "Charles Swindoll"),
    ("The most common way people give up their power is by thinking they don't have any.", "Alice Walker"),
    ("The best revenge is massive success.", "Frank Sinatra"),
    ("Do one thing every day that scares you.", "Eleanor Roosevelt"),
    ("The distance between insanity and genius is measured only by success.", "Bruce Feirstein"),
    ("Don't be afraid to give up the good to go for the great.", "John D. Rockefeller"),
    ("I find that the harder I work, the more luck I seem to have.", "Thomas Jefferson"),
    ("Success is the progressive realization of a worthy goal or ideal.", "Earl Nightingale"),
    ("Don't wish it were easier. Wish you were better.", "Jim Rohn"),
    ("The successful warrior is the average man, with laser-like focus.", "Bruce Lee"),
    ("Take the risk or lose the chance.", "Unknown"),
    ("The way to get started is to quit talking and begin doing.", "Walt Disney"),
    ("Don't let yesterday take up too much of today.", "Will Rogers"),
    ("You learn more from failure than from success. Don't let it stop you. Failure builds character.", "Unknown"),
    ("If you are working on something that you really care about, you don't have to be pushed. The vision pulls you.", "Steve Jobs"),
    ("People who succeed have momentum. The more they succeed, the more they want to succeed.", "Tony Robbins"),
    ("Experience is a hard teacher because she gives the test first, the lesson afterwards.", "Vernon Sanders Law"),
    ("To know how much there is to know is the beginning of learning to live.", "Dorothy West"),
    ("Goal setting is the secret to a compelling future.", "Tony Robbins"),
    ("Concentrate all your thoughts upon the work in hand. The sun's rays do not burn until brought to a focus.", "Alexander Graham Bell"),
    ("Either you run the day or the day runs you.", "Jim Rohn"),
    ("I'm not a product of my circumstances. I am a product of my decisions.", "Stephen Covey"),
    ("Every child is an artist. The problem is how to remain an artist once he grows up.", "Pablo Picasso"),
    ("You can never cross the ocean until you have the courage to lose sight of the shore.", "Christopher Columbus"),
    ("I've learned that people will forget what you said, people will forget what you did, but people will never forget how you made them feel.", "Maya Angelou"),
    ("Either write something worth reading or do something worth writing.", "Benjamin Franklin"),
    ("Certain things catch your eye, but pursue only those that capture the heart.", "Ancient Indian Proverb"),
    ("Everything has beauty, but not everyone can see.", "Confucius"),
    ("How wonderful it is that nobody need wait a single moment before starting to improve the world.", "Anne Frank"),
    ("When I let go of what I am, I become what I might be.", "Lao Tzu"),
    ("Life shrinks or expands in proportion to one's courage.", "Anais Nin"),
    ("If you hear a voice within you say 'you cannot paint,' then by all means paint and that voice will be silenced.", "Vincent Van Gogh"),
    ("There is only one way to avoid criticism: do nothing, say nothing, and be nothing.", "Aristotle"),
    ("Ask and it will be given to you; search, and you will find; knock and the door will be opened for you.", "Jesus Christ"),
    ("The only person you are destined to become is the person you decide to be.", "Ralph Waldo Emerson"),
    ("Go confidently in the direction of your dreams. Live the life you have imagined.", "Henry David Thoreau"),
    ("Few things can help an individual more than to place responsibility on him, and to let him know that you trust him.", "Booker T. Washington"),
    ("The two most important days in your life are the day you are born and the day you find out why.", "Mark Twain"),
    ("Whatever you can do, or dream you can, begin it.  Boldness has genius, power and magic in it.", "Johann Wolfgang von Goethe"),
    ("The best way out is always through.", "Robert Frost"),
    ("The battles that count aren't the ones for gold medals. The struggles within yourself are where the real challenge lies.", "Jesse Owens"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("Fall seven times and stand up eight.", "Japanese Proverb"),
    ("When everything seems to be going against you, remember that the airplane takes off against the wind, not with it.", "Henry Ford"),
    ("Too many of us are not living our dreams because we are living our fears.", "Les Brown"),
    ("Challenges are what make life interesting and overcoming them is what makes life meaningful.", "Joshua J. Marine"),
    ("If you want to lift yourself up, lift up someone else.", "Booker T. Washington"),
    ("I have been impressed with the urgency of doing. Knowing is not enough; we must apply. Being willing is not enough; we must do.", "Leonardo da Vinci"),
    ("Limitations live only in our minds. But if we use our imaginations, our possibilities become limitless.", "Jamie Paolinetti"),
    ("You take your life in your own hands, and what happens? A terrible thing, no one to blame.", "Erica Jong"),
    ("What's money? A man is a success if he gets up in the morning and goes to bed at night and in between does what he wants to do.", "Bob Dylan"),
    ("I didn't fail the test. I just found 100 ways to do it wrong.", "Benjamin Franklin"),
    ("A person who never made a mistake never tried anything new.", "Albert Einstein"),
    ("The person who says it cannot be done should not interrupt the person who is doing it.", "Chinese Proverb"),
    ("There are no traffic jams along the extra mile.", "Roger Staubach"),
    ("It is never too late to be what you might have been.", "George Eliot"),
    ("You become what you believe.", "Oprah Winfrey"),
    ("I would rather die of passion than of boredom.", "Vincent van Gogh"),
    ("A truly rich man is one whose children run into his arms when his hands are empty.", "Unknown"),
    ("It is not what you do for your children, but what you have taught them to do for themselves, that will make them successful human beings.", "Ann Landers"),
    ("If you want your children to turn out well, spend twice as much time with them, and half as much money.", "Abigail Van Buren"),
    ("Build your own dreams, or someone else will hire you to build theirs.", "Farrah Gray"),
    ("The battles that count aren't the ones for gold medals. The struggles within yourself—the invisible battles inside all of us—that's where it's at.", "Jesse Owens"),
    ("Education costs money. But then so does ignorance.", "Sir Claus Moser"),
    ("I have learned over the years that when one's mind is made up, this diminishes fear.", "Rosa Parks"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("If you look at what you have in life, you'll always have more. If you look at what you don't have in life, you'll never have enough.", "Oprah Winfrey"),
    ("Remember that not getting what you want is sometimes a wonderful stroke of luck.", "Dalai Lama"),
    ("You can't use up creativity. The more you use, the more you have.", "Maya Angelou"),
    ("Dream big and dare to fail.", "Norman Vaughan"),
    ("Our lives begin to end the day we become silent about things that matter.", "Martin Luther King Jr."),
    ("Do what you feel in your heart to be right, for you'll be criticized anyway.", "Eleanor Roosevelt"),
]


def _hash_seed(user_id: int, now: datetime) -> int:
    """Create a deterministic seed from user ID, date, and hour."""
    # Include hour for hourly rotation
    seed_str = f"{user_id}-{now.date().isoformat()}-{now.hour}"
    hash_obj = hashlib.md5(seed_str.encode())
    return int(hash_obj.hexdigest()[:8], 16)


def get_todays_quotes(user, count: int = 10) -> Dict[str, Any]:
    """
    Get this hour's quotes for a user.
    
    Uses the user's ID, current date, and current hour to deterministically select
    quotes that rotate every hour. The quotes are spread into "slots" so
    templates can pick which ones to show.
    
    Args:
        user: Django User object (or any object with an 'id' or 'pk' attribute)
        count: Number of quotes to return (default: 10)
    
    Returns:
        Dict with:
        - quotes: List of all selected quotes for this hour
        - slot_1, slot_2, ..., slot_10: Individual quote slots
        - date: Today's date
        - hour: Current hour (for debugging)
    """
    if user is None:
        # Fallback for anonymous users
        user_id = 0
    else:
        user_id = getattr(user, 'id', None) or getattr(user, 'pk', 0)
    
    # Get current time in local timezone (hourly rotation)
    now = timezone.localtime()
    seed = _hash_seed(user_id, now)
    
    # Use seed to select quotes (reproducible for same user + date + hour)
    import random
    rng = random.Random(seed)
    
    # Shuffle a copy of the quotes list
    quotes_pool = list(QUOTES)
    rng.shuffle(quotes_pool)
    
    # Select the first `count` quotes
    selected = quotes_pool[:count]
    
    # Build result with slots
    result = {
        "quotes": [{"text": text, "author": author} for text, author in selected],
        "date": now.date(),
        "hour": now.hour,
        "count": len(selected),
    }
    
    # Add individual slots (slot_1, slot_2, ..., slot_10)
    for i, (text, author) in enumerate(selected, start=1):
        result[f"slot_{i}"] = {"text": text, "author": author}
    
    return result


def get_quote_for_slot(user, slot: int = 1) -> Dict[str, str]:
    """
    Get a single quote for a specific slot.
    
    Args:
        user: Django User object
        slot: Slot number (1-10)
    
    Returns:
        Dict with 'text' and 'author' keys
    """
    quotes_data = get_todays_quotes(user, count=10)
    slot_key = f"slot_{slot}"
    return quotes_data.get(slot_key, {"text": "", "author": ""})

