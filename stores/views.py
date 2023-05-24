from django.shortcuts import render, redirect
from .models import Store, Product, ProductReview
from django.contrib.auth.decorators import login_required
from .forms import *


##### stores
# store 나열
def index(request):
    stores = Store.objects.all()
    context = {
        'stores': stores,
    }
    return render(request, 'stores/index.html', context)

# seller만
def create(request):
    store_form = StoreForm()
    if request.method == 'POST':
        store_form = StoreForm(request.POST, request.FILES)
        if store_form.is_valid():
            store = store_form.save(commit=False)
            store.user = request.user
            store.save()
            return redirect('stores:index')

    context = {
        'store_form': store_form,
    }
    return render(request, 'stores/create.html', context)

# 상품 나열
def detail(request, store_pk):
    products = Product.objects.filter(store=store_pk)
    store = Store.objects.get(pk=store_pk)
    context = {
        'products': products,
        'store': store,
    }
    return render(request, 'stores/detail.html', context)


# 해당하는 seller만
def update(request, store_pk):
    if request.method == 'POST':
        pass
        # return redirect('stores:detail',) # store.pk
    return render(request, 'stores/update.html')


# 해당하는 seller만
def delete(request, store_pk):
    return redirect('stores:index')



##### products
# 해당하는 seller만
def products_create(request, store_pk):
    store = Store.objects.get(pk=store_pk)
    if request.method == 'POST':
        product_form = ProductForm(request.POST)
        if product_form.is_valid():
            product = product_form.save(commit=False)
            product.store = store
            product.save()
            for image in request.FILES.getlist('image'):
                # print(image)
                # image = ProductImage(request.POST)
                # image.product = product
                # image.image = image
                # image.save()
                ProductImage.objects.create(image=image, product=product) 
            return redirect('stores:products_detail', store.pk, product.pk)
    else:
        product_form = ProductForm()
        image_form = ProductImageForm()
    context = {
        'product_form': product_form,
        'image_form': image_form,
        'store': store,
    }
    return render(request, 'stores/products_create.html', context)


def products_detail(request, store_pk, product_pk):
    store = Store.objects.get(pk=store_pk)
    product = Product.objects.get(pk=product_pk)
    reviews = ProductReview.objects.filter(product=product_pk)
    context = {
        'store': store,
        'product': product,
        'reviews': reviews,
    }
    return render(request, 'stores/products_detail.html', context)


# 해당하는 seller만
def products_update(request, store_pk, product_pk):
    return render(request, 'stores/products_update.html')


# 해당하는 seller만
def products_delete(request, store_pk, product_pk):
    return redirect('stores:detail', store_pk)


##### reviews





##### cart

# def add_to_cart(request, product_id):
#     cart = request.session.get('cart', {})  # Retrieve the cart data from the session
#     quantity = cart.get(product_id, 0) + 1
#     cart[product_id] = quantity
#     request.session['cart'] = cart  # Store the updated cart data in the session under 'cart' key
#     return redirect('cart')


# def cart(request):
#     cart = request.session.get('cart', {})
#     product_ids = cart.keys()
#     products = Product.objects.filter(id__in=product_ids)
#     context = {'cart': cart, 'products': products}
#     return render(request, 'cart.html', context)


# def remove_from_cart(request, product_id):
#     cart = request.session.get('cart', {})
#     if product_id in cart:
#         del cart[product_id]
#         request.session['cart'] = cart  # Update the cart data in the session
#     return redirect('cart')


# def update_quantity(request, product_id):
#     cart = request.session.get('cart', {})
#     new_quantity = request.POST.get('quantity')  # Retrieve the new quantity from the request
#     if new_quantity:
#         cart[product_id] = int(new_quantity)
#         request.session['cart'] = cart  # Update the cart data in the session
#     return redirect('cart')
