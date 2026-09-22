
class BuyerSignupView(UserAlreadyLoggedInMixin, FormView):
    template_name = 'auth/buyer-signup.html'
    form_class = BuyerSignupForm
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        data = form.cleaned_data
        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            telegram_id=data['telegram_id'],
            password=data['password'],
            first_name=data['full_name'],
            user_type=UserType.BUYER
        )
        Buyer.objects.create(user=user)
        login(self.request, user)
        CartService(self.request).sync_to_db(user)
        FavoriteService(self.request).sync_to_db(user)
        SponsoredAdClickService(self.request).sync_to_db(user)
        return super().form_valid(form)

class LoginView(UserAlreadyLoggedInMixin, View):
    template_name = 'auth/login.html'

    def get(self, request):
        buyer_form = BuyerLoginForm()
        seller_form = SellerLoginForm()
        return render(request, self.template_name, {
            'buyer_form': buyer_form,
            'seller_form': seller_form
        })

    def post(self, request):
        login_type = request.POST.get('login_type')
        buyer_form = BuyerLoginForm()
        seller_form = SellerLoginForm()

        if login_type == 'buyer':
            form = BuyerLoginForm(request.POST)
            buyer_form = form
            if form.is_valid():
                user = form.cleaned_data['user']
                login(request, user)
                CartService(request).sync_to_db(user)
                FavoriteService(request).sync_to_db(user)
                SponsoredAdClickService(request).sync_to_db(user)
                return redirect('home')
        elif login_type == 'seller':
            form = SellerLoginForm(request.POST)
            seller_form = form
            if form.is_valid():
                user = form.cleaned_data['user']
                login(request, user)
                CartService(request).sync_to_db(user)
                FavoriteService(request).sync_to_db(user)
                return redirect('vendor_dashboard')
        
        return render(request, self.template_name, {
            'buyer_form': buyer_form,
            'seller_form': seller_form
        })

class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('home')

class OtpCodeView(FormView):
    template_name = 'auth/otp.html'
    form_class = OTPForm
    success_url = reverse_lazy('verify_otp')

    def form_valid(self, form):
        email = form.cleaned_data['email']
        user = User.objects.get(email=email)
        
        # Create OTP for Password Reset
        otp_code = user.create_otp(code_type=CodeTypes.RESET_PASSWORD)
        self.request.session['signup_email'] = email
        
        # Send OTP Email
        send_otp_email(otp_code, email)
        
        return super().form_valid(form)


class VerifyOtpView(View):
    template_name = 'auth/verify.html'
    
    def get(self, request):
        form = VerifyOTPForm()
        email = request.session.get('signup_email')
        return render(request, self.template_name, {
            'form': form, 
            'email': email
        })

    def post(self, request):
        form = VerifyOTPForm(request.POST)
        email = request.session.get('signup_email')
        
        if form.is_valid():
            code = form.cleaned_data['code']
            otp = OTPCode.objects.filter(email=email, code=code, is_used=False).first()
            
            if otp and not otp.is_expired:
                otp.is_used = True
                otp.save()
                
                if email:
                    try:
                        user = User.objects.get(email=email)
                        if user:
                            user.is_verified = True
                            user.save()
                            authenticate(request, username=user.email, password=None)
                            login(request, user)
                            if user.user_type == UserType.SELLER:
                                return redirect('vendor_dashboard')
                    except User.DoesNotExist:
                        pass
                return redirect('home')
            
            form.add_error('code', "رمز التحقق غير صحيح أو منتهي الصلاحية.")
        
        return render(request, self.template_name, {
            'form': form, 
            'email': email
        })


class ChangePasswordView(LoginRequiredMixin, View):
    def get(self, request):
        form = ChangePasswordForm(user=request.user)
        return render(request, "auth/change_password.html", {'form':form})

    def post(self, request):
        form = ChangePasswordForm(request.POST, user=request.user)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important to stay logged in
            return redirect('home')
        return render(request, "auth/change_password.html", {'form':form})
